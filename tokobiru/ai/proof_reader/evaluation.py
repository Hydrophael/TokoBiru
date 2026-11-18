import re
from datetime import datetime, timedelta
from .parsing import TZ_NAMES
from .comparison import _status_kind, compare_readings, proof_fingerprint


MIN_CONFIDENCE = 0.6                       # di bawah ini hasilnya "perlu dicek", apa pun isinya


TIME_TOLERANCE = timedelta(minutes=5)      # selisih jam HP/bank yang masih wajar


# Bila struk TIDAK mencetak zona waktu, jam dibaca sebagai WIB, padahal pelanggan di WITA (+1 jam) atau WIT (+2 jam)
# mencetak jam setempat, jadi batas "di masa depan" dilonggarkan. Bila zona tercetak, dipakai toleransi ketat.
FUTURE_TOLERANCE = timedelta(hours=2, minutes=5)


WIB_OFFSET = timedelta(hours=7)            # struk bank di Indonesia mencetak jam setempat; server memakai UTC


REVISION_LIMIT = 4                         # foto bukti diunggah/diganti sebanyak ini atau lebih = mencurigakan


# --- Menilai: aturan biasa, bukan model ----------------------------------------------------------------------

def _rupiah(amount):
    return "Rp" + f"{amount:,}".replace(",", ".")


# Kata bank/e-wallet dan kata sambung rekening: bukan nama pemilik, jadi tidak dihitung sebagai bukti nama
_BANK_WORDS = {"bank", "rekening", "rek", "norek", "bca", "bri", "bni", "mandiri", "bsi", "cimb", "jago", "seabank",
               "dana", "gopay", "ovo", "shopeepay", "linkaja", "qris", "atas", "nama", "no", "an"}


def _name_key(text):
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def _owner_name(destination):
    words = [w for w in re.findall(r"[a-z]+", destination.casefold()) if w not in _BANK_WORDS]
    return "".join(words)


def destination_status(destination, hint):
    """'ok' bila tujuan di struk cocok dengan ciri rekening toko, 'bad' bila jelas berbeda, 'unknown' bila struk tidak
    memuat jenis data yang sama dengan hint (mis. hint berupa angka tetapi struk hanya mencetak nama).

    Hint boleh beberapa, dipisah koma: '4821,TokoBiru'. Angka (3+ digit) dicocokkan sebagai akhiran nomor rekening per
    kelompok angka, bukan sebagai potongan di mana saja (aman untuk nomor tersamar ****4821, dan nomor lain yang kebetulan
    memuat 4821 di tengah tidak lolos). Nama dicocokkan tanpa spasi/tanda baca dan tanpa memandang huruf besar-kecil;
    nama yang dipotong bank ('TOKOBIR') tetap diterima."""
    groups = [g for g in re.findall(r"\d+", destination) if len(g) >= 3]
    owner = _owner_name(destination)
    dest_key = _name_key(destination)
    digit_hints, name_hints = [], []
    for part in hint.split(","):
        part = part.strip()
        digits = re.sub(r"\D", "", part)
        if len(digits) >= 3:
            digit_hints.append(digits)
        elif _name_key(part):
            name_hints.append(_name_key(part))
    for h in digit_hints:
        if any(g.endswith(h) or h.endswith(g) for g in groups):
            return "ok"
    for h in name_hints:
        if h in dest_key or (len(owner) >= 5 and owner in h):
            return "ok"
    if (digit_hints and groups) or (name_hints and len(owner) >= 4):
        return "bad"
    return "unknown"


def _matches_hint(destination, hint):
    return destination_status(destination, hint) == "ok"


ADVICE = {
    "not_successful": "Struk menunjukkan transaksi belum berhasil (pending atau gagal). Cek mutasi rekening sebelum menandai dibayar.",
    "match": "Semua data cocok. Cocokkan dengan mutasi rekening, lalu tandai dibayar.",
    "mismatch": "Ada data yang tidak cocok dengan pesanan. Cek mutasi rekening, atau minta pelanggan memperbaiki pembayarannya.",
    "suspicious": "Ada tanda bukti lama atau dipakai ulang. Cek mutasi rekening sebelum menandai dibayar.",
    "tampered": "Ada tanda foto diedit atau diganti berkali-kali. Cek mutasi rekening sebelum menandai dibayar.",
    "inconsistent": "Dua kali pembacaan AI memberi hasil berbeda, jadi hasilnya belum bisa dipercaya. Cek manual atau coba baca lagi.",
    "unclear": "Foto kurang jelas untuk disimpulkan otomatis. Cek manual atau minta foto yang lebih jelas.",
    "not_proof": "Foto ini tampaknya bukan bukti transfer. Minta pelanggan mengirim bukti yang benar.",
}


DECISIVE = ("match", "mismatch", "suspicious")


def evaluate_proof(reading, *, total, created_at, now, bank_hint="", duplicate=False, uploaded_at=None, revision=1,
                   second=None):
    """Bandingkan hasil baca dengan pesanan. created_at, now, uploaded_at dalam UTC (naive), seperti di app.py.
    second = pembacaan kedua atas foto yang sama (opsional); bila berbeda, hasil yang menentukan diturunkan jadi unclear.

    Hasil: {verdict, confidence (0-100), checks[], advice, reason, reference, ...}. verdict salah satu dari
    match | mismatch | suspicious | unclear. Urutan prioritas: foto bukan bukti / keyakinan rendah -> unclear;
    status transaksi belum berhasil -> mismatch; dipakai ulang -> suspicious; tanda diedit / diunggah berkali-kali -> suspicious;
    nominal atau tujuan salah -> mismatch; waktu janggal -> suspicious; ada yang tak terbaca -> unclear; selebihnya match.
    Dua pembacaan yang berbeda menurunkan hasil menentukan menjadi unclear."""
    checks = []

    def add(key, label, read, expected, status, note):
        checks.append({"key": key, "label": label, "read": read, "expected": expected, "status": status, "note": note})

    amount = reading["amount"]
    if amount is None:
        add("amount", "Nominal", "tidak terbaca", _rupiah(total), "unknown", f"Tagihan {_rupiah(total)}")
    elif amount == total:
        add("amount", "Nominal", _rupiah(amount), _rupiah(total), "ok", f"Sama dengan tagihan {_rupiah(total)}")
    else:
        diff = amount - total
        word = "Lebih" if diff > 0 else "Kurang"
        add("amount", "Nominal", _rupiah(amount), _rupiah(total), "bad", f"{word} {_rupiah(abs(diff))} dari tagihan")

    local_time = reading["time"]
    if local_time is None:
        add("time", "Waktu transfer", "tidak terbaca", "", "unknown", "Harus setelah pesanan dibuat")
    else:
        offset = reading.get("timezone")
        # Zona tercetak: toleransi ketat. Tidak tercetak: dibaca WIB dengan batas masa depan longgar (pelanggan WITA/WIT)
        zone_hours, future_tolerance = (offset, TIME_TOLERANCE) if offset else (7, FUTURE_TOLERANCE)
        as_utc = local_time - timedelta(hours=zone_hours)
        shown = local_time.strftime("%Y-%m-%d %H:%M") + " " + TZ_NAMES[zone_hours]
        # Batas atas = saat foto diunggah (transfer tak mungkin terjadi setelah buktinya diunggah), bukan saat dibaca
        upper = min(now, uploaded_at) if uploaded_at else now
        if as_utc < created_at - TIME_TOLERANCE:
            add("time", "Waktu transfer", shown, "", "bad", "Sebelum pesanan dibuat")
        elif as_utc > upper + future_tolerance:
            add("time", "Waktu transfer", shown, "", "bad", "Waktunya belum terjadi")
        else:
            add("time", "Waktu transfer", shown, "", "ok", "Setelah pesanan dibuat")

    if bank_hint:
        destination = reading["destination"]
        if destination is None:
            add("destination", "Tujuan", "tidak terbaca", bank_hint, "unknown", "Rekening toko tidak bisa dipastikan")
        else:
            state = destination_status(destination, bank_hint)
            notes = {"ok": "Sesuai rekening toko", "bad": "Bukan rekening toko",
                     "unknown": "Struk tidak memuat data yang bisa dicocokkan dengan rekening toko"}
            add("destination", "Tujuan", destination, bank_hint, state, notes[state])
    else:
        add("destination", "Tujuan", reading["destination"] or "tidak terbaca", "", "skip",
            "Rekening toko belum diatur (PROOF_BANK_HINT kosong), jadi tujuan tidak diperiksa")

    kind = _status_kind(reading.get("status"))
    if kind == "bad":
        add("status", "Status transaksi", reading["status"], "Berhasil", "bad", "Transaksi belum berhasil")
    elif kind == "ok":
        add("status", "Status transaksi", reading["status"], "Berhasil", "ok", "Transaksi berhasil")

    if duplicate:
        add("duplicate", "Keaslian", "pernah dipakai", "", "bad", "Foto, nomor referensi, atau nominal+jam sama dengan pesanan lain")
    else:
        add("duplicate", "Keaslian", "belum pernah dipakai", "", "ok", "Tidak ada pesanan lain dengan foto atau referensi sama")

    if revision >= REVISION_LIMIT:
        add("revisions", "Riwayat unggah", f"{revision} kali unggah", "", "bad", "Foto bukti diganti berkali-kali")
    if reading.get("edited"):
        add("edited", "Tanda edit", reading.get("edit_note") or "terlihat", "", "bad", "AI melihat tanda teks diubah di foto")

    disagree = []
    if second is not None:
        disagree = compare_readings(reading, second)
        if disagree:
            add("consistency", "Konsistensi baca", "berbeda: " + ", ".join(disagree), "", "bad", "Dua pembacaan AI tidak sama")
        else:
            add("consistency", "Konsistensi baca", "dua kali sama", "", "ok", "Dua pembacaan AI memberi hasil yang sama")

    status = {check["key"]: check["status"] for check in checks}
    if not reading["is_proof"]:
        verdict, advice_key = "unclear", "not_proof"
    elif reading["confidence"] < MIN_CONFIDENCE:
        verdict, advice_key = "unclear", "unclear"
    elif status.get("status") == "bad":
        verdict, advice_key = "mismatch", "not_successful"
    elif status["duplicate"] == "bad":
        verdict, advice_key = "suspicious", "suspicious"
    elif "bad" in (status.get("revisions"), status.get("edited")):
        verdict, advice_key = "suspicious", "tampered"
    elif "bad" in (status["amount"], status["destination"]):
        verdict, advice_key = "mismatch", "mismatch"
    elif status["time"] == "bad":
        verdict, advice_key = "suspicious", "suspicious"
    elif "unknown" in status.values():
        verdict, advice_key = "unclear", "unclear"
    else:
        verdict, advice_key = "match", "match"
    if verdict in DECISIVE and disagree:
        verdict, advice_key = "unclear", "inconsistent"

    advice = ADVICE[advice_key]
    if advice_key == "match" and status["destination"] == "skip":
        advice += " Rekening tujuan belum diperiksa karena PROOF_BANK_HINT belum diisi."

    return {
        "verdict": verdict,
        "confidence": round(reading["confidence"] * 100),
        "checks": checks,
        "advice": advice,
        "reason": advice_key,          # match | mismatch | suspicious | tampered | inconsistent | unclear | not_proof | not_successful
        "reference": reading["reference"],
        "fingerprint": proof_fingerprint(reading),
        "reads": 2 if second is not None else 1,
        "confirmed": second is not None and not disagree,
        "disagree": disagree,
        "ungrounded": list(reading.get("ungrounded") or []),
    }
