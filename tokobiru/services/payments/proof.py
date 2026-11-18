from flask import current_app
import hashlib
import time
from tokobiru.core.config import GEMINI_API_KEY, PROOF_BANK_HINT, PROOF_CONFIRM_MIN_SECONDS, PROOF_CONFIRM_READ, PROOF_READER_FALLBACK_MODEL, PROOF_READER_MODEL
from tokobiru.core.security import audit
from tokobiru.core.util import utcnow
from tokobiru.ai.proof_reader import ProofReadError, evaluate_proof, proof_fingerprint, read_transfer_proof


def proof_is_reused(db, order_id, digest, reference, fingerprint=None):
    # Foto yang sama persis, nomor referensi transfer yang sama, atau (bila referensi tak terbaca) nominal+menit yang sama
    # sudah dipakai di pesanan lain. Sidik jari nominal+menit menangkap struk yang sama dengan byte berbeda (disimpan ulang,
    # dipotong, tangkapan layar dari tangkapan layar) yang lolos dari pemeriksaan sha256.
    if db.order_proofs.find_one({"sha256": digest, "_id": {"$ne": order_id}}, {"_id": 1}):
        return True
    if reference and len(reference) >= 6:
        return bool(db.orders.find_one({"proof_check.reference": reference, "_id": {"$ne": order_id}}, {"_id": 1}))
    if fingerprint:
        return bool(db.orders.find_one({"proof_check.fingerprint": fingerprint, "_id": {"$ne": order_id}}, {"_id": 1}))
    return False


def read_proof_model(image, mime, model, timeout, thinking):
    """Satu pembacaan oleh satu model. Sebagian model (mis. varian lite) menolak tingkat berpikir "medium" dengan HTTP 400:
    bukan alasan menggagalkan pembacaan, jadi diulang sekali dengan "low" dalam sisa waktu yang sama."""
    started = time.monotonic()
    try:
        return read_transfer_proof(image, mime, GEMINI_API_KEY, model, timeout=timeout, thinking=thinking)
    except ProofReadError as exc:
        left = timeout - (time.monotonic() - started)
        if exc.status == 400 and thinking != "low" and left >= 2:
            current_app.logger.warning("Model %s menolak thinking=%s (400), diulang dengan low", model, thinking)
            return read_transfer_proof(image, mime, GEMINI_API_KEY, model, timeout=left, thinking="low")
        raise


def read_with_fallback(image, mime, timeout, thinking):
    """Baca dengan model utama; bila server AI sibuk (503/429/5xx) atau kena batas waktu coba model cadangan dalam sisa waktu yang sama.
    Mengembalikan (hasil_baca, nama_model_yang_dipakai). Galat selain itu (kunci salah, foto ditolak, dll.) tidak dicoba ulang."""
    started = time.monotonic()
    models = [PROOF_READER_MODEL]
    if PROOF_READER_FALLBACK_MODEL and PROOF_READER_FALLBACK_MODEL != PROOF_READER_MODEL:
        models.append(PROOF_READER_FALLBACK_MODEL)
    last = None
    # Model utama tidak boleh menghabiskan seluruh waktu: bila ada cadangan dan waktunya longgar (baca manual staf),
    # sisakan sepertiganya supaya batas waktu pada model utama tetap bisa diselamatkan model cadangan
    primary_timeout = timeout * 0.65 if len(models) > 1 and timeout >= 12 else timeout
    for index, model in enumerate(models):
        left = timeout - (time.monotonic() - started)
        if index and left < 2:
            break
        attempt_started = time.monotonic()
        try:
            reading = read_proof_model(image, mime, model, left if index else primary_timeout, thinking)
            took = time.monotonic() - attempt_started
            if took > 5:   # petunjuk untuk menyetel batas waktu dan model: pembacaan selambat ini patut dicatat
                current_app.logger.warning("Model %s butuh %.1f dtk untuk membaca bukti (thinking=%s)", model, took, thinking)
            return reading, model
        except ProofReadError as exc:
            last = exc
            if not exc.retryable:
                break
            current_app.logger.warning("Model %s sibuk (%s)%s", model, exc,
                               ", mencoba model cadangan" if index + 1 < len(models) else "")
    raise last


def confirm_reading(image, mime, first_model, started, timeout, thinking):
    """Bacaan kedua atas foto yang sama, oleh model LAIN bila ada (bila tidak, model yang sama), untuk dibandingkan dengan
    bacaan pertama. Mengembalikan None bila waktu tidak cukup atau gagal: hasil tetap dipakai, hanya ditandai belum terkonfirmasi."""
    other = [m for m in (PROOF_READER_MODEL, PROOF_READER_FALLBACK_MODEL) if m and m != first_model]
    model = other[0] if other else first_model
    left = timeout - (time.monotonic() - started)
    if left < PROOF_CONFIRM_MIN_SECONDS:
        return None
    try:
        return read_proof_model(image, mime, model, left, thinking)
    except ProofReadError as exc:
        current_app.logger.warning("Bacaan kedua (%s) gagal: %s", model, str(exc)[:200])
        return None


def analyze_proof(db, order, proof, actor, timeout=8, deep=False):
    """Baca foto bukti lewat AI, nilai dengan aturan biasa, simpan hasilnya di pesanan, lalu kembalikan.
    Dipakai oleh unggahan pelanggan (otomatis, cepat) dan tombol staf (manual, deep=True: berpikir lebih teliti).
    Hasil yang menentukan (cocok / tidak cocok / mencurigakan) dibaca dua kali oleh model berbeda; bila keduanya tidak sama,
    hasilnya diturunkan menjadi "Perlu dicek". Melempar ProofReadError bila AI gagal."""
    image = bytes(proof["image"])
    mime = proof.get("type") or "image/jpeg"
    thinking = "medium" if deep else "low"
    started = time.monotonic()
    reading, model_used = read_with_fallback(image, mime, timeout, thinking)
    digest = hashlib.sha256(image).hexdigest()
    now = utcnow()
    fingerprint = proof_fingerprint(reading)
    duplicate = proof_is_reused(db, order["_id"], digest, reading["reference"],
                                fingerprint if not reading["reference"] else None)
    rules = dict(total=order["total"], created_at=order["created_at"], now=now, bank_hint=PROOF_BANK_HINT,
                 duplicate=duplicate, uploaded_at=order["proof_at"], revision=proof.get("revision") or 1)
    result = evaluate_proof(reading, **rules)
    if PROOF_CONFIRM_READ and result["verdict"] != "unclear":
        second = confirm_reading(image, mime, model_used, started, timeout, thinking)
        if second is not None:
            result = evaluate_proof(reading, second=second, **rules)
    if not PROOF_CONFIRM_READ:
        result["confirmed"] = None   # bacaan kedua dimatikan: bukan "gagal dikonfirmasi", jadi tidak ada tombol verifikasi ulang
    result.update(proof_at=order["proof_at"], read_at=now, model=model_used)
    db.order_proofs.update_one({"_id": order["_id"]}, {"$set": {"sha256": digest}})   # melengkapi bukti lama
    db.orders.update_one({"_id": order["_id"], "proof_at": order["proof_at"]}, {"$set": {"proof_check": result}})
    unconfirmed = result["confirmed"] is False and result["verdict"] != "unclear"
    audit("bukti_dibaca", f"{order['code']}: {result['verdict']}" + (" (belum terkonfirmasi)" if unconfirmed else ""), actor)
    return result
