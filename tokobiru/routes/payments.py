import hashlib
import secrets

from flask import Blueprint, Response, current_app, jsonify, request

from tokobiru.ai.proof_reader import ProofReadError
from tokobiru.core.config import (
    DUMMY_QRIS,
    EWALLET_CHANNELS,
    PROOF_AUTO_READS_PER_HOUR,
    PROOF_CONFIRM_READ,
    PROOF_READER_ENABLED,
    PROOF_STAFF_READS_PER_HOUR,
    PROOF_STAFF_TIMEOUT,
    PROOF_UPLOAD_TIMEOUT,
    PROOF_UPLOADS_PER_HOUR,
    PROOF_VERDICT_TEXT,
    STAFF_ROLES,
    SYSTEM_ACTOR,
    XENDIT_CALLBACK_TOKEN,
    XENDIT_ENABLED,
    XENDIT_SIMULATE_SCAN,
)
from tokobiru.core.connection import get_db
from tokobiru.core.security import (
    _hit,
    audit,
    client_ip,
    current_user,
    login_required,
    proof_read_quota,
    roles_required,
)
from tokobiru.core.serializers import order_json
from tokobiru.core.util import format_rupiah, utcnow
from tokobiru.core.validation import PROOF_IMAGE_MAX_CHARS, Form, json_body, object_id
from tokobiru.errors import ApiError
from tokobiru.services.notifications import push_staff
from tokobiru.services.orders.expiry import (
    cancel_expired_order,
    settle_overdue,
    sweep_expired_orders,
)
from tokobiru.services.payments.proof import analyze_proof
from tokobiru.services.payments.qris import (
    PAY_TOKEN_RE,
    QRIS_ACTOR,
    mark_order_paid,
    qris_page,
)
from tokobiru.services.payments.xendit import (
    XENDIT_ACTOR,
    XENDIT_PAID_STATUS,
    GatewayError,
    sync_ewallet_status,
    xendit_request,
)

bp = Blueprint("payments", __name__)


@bp.get("/pay/<token>")
def qris_scan(token):
    # Tanpa login: token acak di tautan inilah yang membuktikan pemilik pesanan
    missing = lambda: qris_page(False, "Tautan tidak ditemukan", ["Kode QR ini tidak berlaku."], 404)
    if not (DUMMY_QRIS or XENDIT_SIMULATE_SCAN) or not PAY_TOKEN_RE.fullmatch(token):
        return missing()
    db = get_db()
    order = db.orders.find_one({"pay_token": token})
    if not order:
        return missing()
    order = settle_overdue(db, order)
    if order["status"] == "cancelled":
        return qris_page(False, "Pesanan dibatalkan",
                         [f"Pesanan {order['code']} sudah dibatalkan atau kedaluwarsa.", "Silakan buat pesanan baru."], 410)
    if order["status"] == "pending":
        if XENDIT_SIMULATE_SCAN and order.get("qr_id"):
            try:
                xendit_request("POST", f"/qr_codes/{order['qr_id']}/payments/simulate",
                               {"amount": order["total"]})
            except GatewayError:
                return qris_page(False, "Simulasi gagal", ["Xendit tidak merespons. Coba scan lagi."], 502)
        mark_order_paid(db, order, "xendit" if XENDIT_SIMULATE_SCAN else "qris", QRIS_ACTOR)
    return qris_page(True, "Pembayaran berhasil", [format_rupiah(order["total"]), f"Pesanan {order['code']}"])


@bp.post("/api/orders/<order_id>/proof")
@roles_required("user")
def order_proof_upload(order_id):
    # Bukti transfer disimpan di koleksi terpisah (kunci = id pesanan) supaya daftar pesanan tidak ikut memuat gambar
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"] or order.get("payment_method") != "transfer":
        raise ApiError("Pesanan tidak ditemukan", 404)
    order = settle_overdue(db, order)
    if order["status"] != "pending":
        raise ApiError("Bukti hanya bisa diunggah selama pesanan belum dibayar", 409)
    if _hit(f"rl:proofup:{user['_id']}", 3600) > PROOF_UPLOADS_PER_HOUR:
        raise ApiError("Terlalu banyak unggahan bukti dalam satu jam. Coba lagi nanti.", 429)
    form = Form(json_body())
    form.image("image", "Bukti transfer", PROOF_IMAGE_MAX_CHARS)
    clean = form.done()
    if not clean.get("image"):
        raise ApiError("Periksa kembali isian Anda", 422, {"image": "Pilih foto bukti transfer"})
    data, mime = clean["image"]
    now = utcnow()
    # Berapa kali foto bukti pesanan ini diunggah/diganti: mengulang sampai AI "setuju" adalah tanda mencurigakan
    previous = db.order_proofs.find_one({"_id": order["_id"]}, {"revision": 1})
    revision = (previous.get("revision") or 1) + 1 if previous else 1
    db.order_proofs.replace_one({"_id": order["_id"]},
                                {"_id": order["_id"], "image": data, "type": mime, "uploaded_at": now,
                                 "sha256": hashlib.sha256(bytes(data)).hexdigest(), "revision": revision}, upsert=True)
    # Foto baru: hasil baca foto lama tidak berlaku lagi
    db.orders.update_one({"_id": order["_id"], "status": "pending"},
                         {"$set": {"proof_at": now, "updated_at": now}, "$unset": {"proof_check": "", "proof_remind_sent": ""}})
    order = db.orders.find_one({"_id": order["_id"]})   # ambil ulang: Mongo menyimpan waktu dengan ketelitian milidetik
    audit("bukti_transfer", order["code"])

    # Baca otomatis saat unggah. Kegagalan AI tidak boleh menggagalkan unggahan: staf masih punya tombol manual.
    verdict_note = ""
    if PROOF_READER_ENABLED and order.get("proof_at") and proof_read_quota(user, PROOF_AUTO_READS_PER_HOUR):
        try:
            result = analyze_proof(db, order, {"image": data, "type": mime, "revision": revision}, SYSTEM_ACTOR,
                                    timeout=PROOF_UPLOAD_TIMEOUT)
            verdict_note = f" · {PROOF_VERDICT_TEXT.get(result['verdict'], 'Perlu dicek')} ({result['confidence']}%)"
        except Exception as exc:
            current_app.logger.warning("Baca otomatis saat unggah gagal (%s): %s", order["code"], str(exc)[:200])

    push_staff("Bukti transfer masuk",
               f"{order['code']} · {format_rupiah(order['total'])}{verdict_note}. Cocokkan dengan mutasi, lalu tandai dibayar.",
               f"order-{order['code']}-bukti")
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


@bp.get("/api/orders/<order_id>/proof")
@login_required
def order_proof_view(order_id):
    # Hanya pemilik pesanan dan admin
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or (user["role"] == "user" and order["user_id"] != user["_id"]):
        raise ApiError("Bukti tidak ditemukan", 404)
    proof = db.order_proofs.find_one({"_id": order["_id"]})
    if not proof:
        raise ApiError("Bukti tidak ditemukan", 404)
    resp = Response(bytes(proof["image"]), mimetype=proof.get("type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Content-Disposition"] = "inline"
    return resp


@bp.post("/api/orders/<order_id>/proof/check")
@roles_required(*STAFF_ROLES)
def order_proof_check(order_id):
    # Cadangan manual: dipakai bila pembacaan saat unggah gagal, atau untuk bukti lama yang diunggah sebelum fitur ada
    if not PROOF_READER_ENABLED:
        raise ApiError("Pembacaan otomatis belum diaktifkan", 503)
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order.get("payment_method") != "transfer":
        raise ApiError("Pesanan tidak ditemukan", 404)
    proof = db.order_proofs.find_one({"_id": order["_id"]})
    if not proof or not order.get("proof_at"):
        raise ApiError("Belum ada bukti transfer untuk dibaca", 404)
    cached = order.get("proof_check")
    body = request.get_json(silent=True)
    # Boleh dicoba lagi: hasil "Perlu dicek", atau hasil yang menentukan tetapi belum terkonfirmasi bacaan kedua
    # (confirmed None = bacaan kedua dimatikan atau hasil lama sebelum fitur ini: bukan alasan untuk membaca ulang)
    retryable = bool(cached) and (cached.get("verdict") == "unclear" or
                                  (PROOF_CONFIRM_READ and cached.get("confirmed") is False))
    retry = isinstance(body, dict) and body.get("force") is True and retryable
    if cached and cached.get("proof_at") == order["proof_at"] and not retry:
        return jsonify({"order": order_json(order, user)})   # foto ini sudah dibaca: tidak memanggil AI lagi
    # Pembacaan ulang (force) tetap dihitung dalam batas baca per jam
    if not proof_read_quota(user, PROOF_STAFF_READS_PER_HOUR):
        raise ApiError("Terlalu banyak pembacaan dalam satu jam. Coba lagi nanti atau cek manual.", 429)
    try:
        analyze_proof(db, order, proof, user, timeout=PROOF_STAFF_TIMEOUT, deep=True)
    except ProofReadError as exc:
        current_app.logger.error("Baca bukti %s gagal: %s", order["code"], exc)
        if exc.status == 429:
            raise ApiError("Kuota layanan AI sedang habis. Tunggu beberapa menit, atau cek manual.", 502)
        if exc.transient:
            raise ApiError("Layanan AI terlalu lama menjawab. Coba lagi, atau cek manual.", 502)
        if exc.retryable:
            raise ApiError("Layanan AI sedang sibuk. Coba lagi beberapa saat lagi, atau cek manual.", 502)
        raise ApiError("Bukti belum bisa dibaca otomatis. Cek manual.", 502)
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


@bp.get("/api/orders/<order_id>/status")
@login_required
def order_status_poll(order_id):
    db = get_db()
    sweep_expired_orders(db)
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or (user["role"] == "user" and order["user_id"] != user["_id"]):
        raise ApiError("Pesanan tidak ditemukan", 404)
    order = sync_ewallet_status(db, settle_overdue(db, order))
    return jsonify({"status": order["status"]})


@bp.post("/api/orders/<order_id>/simulate-pay")
@roles_required("user")
def order_simulate_pay(order_id):
    if not DUMMY_QRIS:
        raise ApiError("QRIS tidak aktif", 404)
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"] or order.get("payment_method") != "qris":
        raise ApiError("Pesanan tidak ditemukan", 404)
    order = settle_overdue(db, order)
    if order["status"] == "cancelled":
        raise ApiError("Pesanan sudah dibatalkan atau kedaluwarsa", 409)
    mark_order_paid(db, order, "qris")
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


@bp.post("/webhooks/xendit")
def xendit_webhook():
    # Di luar /api/ karena dipanggil server Xendit (tanpa sesi dan token CSRF); keasliannya dibuktikan oleh x-callback-token
    if not XENDIT_ENABLED:
        return jsonify({"error": "tidak aktif"}), 404
    sent = request.headers.get("x-callback-token", "")
    if not secrets.compare_digest(sent.encode(), XENDIT_CALLBACK_TOKEN.encode()):
        current_app.logger.warning("Webhook Xendit ditolak: token salah dari %s", client_ip())
        return jsonify({"error": "token tidak valid"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "format tidak valid"}), 400

    event = payload.get("event")
    data = payload["data"] if isinstance(payload.get("data"), dict) else payload
    is_ewallet = event == "ewallet.capture"
    reference, qr_id = data.get("reference_id"), data.get("qr_id")
    amount = data.get("charge_amount", data.get("amount")) if is_ewallet else data.get("amount")
    status = str(data.get("status", "")).upper()
    paid = status in XENDIT_PAID_STATUS
    # E-wallet ditolak pelanggan atau tagihan kedaluwarsa di sisi e-wallet
    failed = is_ewallet and status == "FAILED"
    # Event lain (mis. refund) dan status selain lunas diabaikan; 200 supaya Xendit tidak mengirim ulang
    if (event and event not in ("qr.payment", "ewallet.capture")) or not (paid or failed) or not isinstance(reference, str):
        # Token sudah terbukti benar di atas, jadi aman dicatat (bukan lalu lintas liar); membantu melacak notifikasi yang tidak melunasi
        audit("webhook_diabaikan", f"{event or '-'} {status or '-'} {str(reference)[:40]}", XENDIT_ACTOR)
        return jsonify({"ok": True, "ignored": True}), 200

    db = get_db()
    if is_ewallet:
        order = db.orders.find_one({"code": reference, "payment_method": {"$in": list(EWALLET_CHANNELS)}})
        # Nomor transaksi e-wallet harus sama dengan yang tersimpan di pesanan
        if order and order.get("ewallet_id") and data.get("id") and data["id"] != order["ewallet_id"]:
            order = None
    else:
        order = db.orders.find_one({"code": reference, "payment_method": "qris"})
    if not order:
        audit("pembayaran_tak_dikenal", reference[:40], XENDIT_ACTOR)
        return jsonify({"ok": True, "ignored": True}), 200

    if failed:
        # Batalkan sekarang supaya stok tidak tertahan sampai batas waktu toko habis; bila sudah tidak pending, tidak ada yang berubah
        cancel_expired_order(db, order, "payment_failed", "pesanan_bayar_gagal")
        return jsonify({"ok": True})

    amount_ok = isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount == order["total"]
    qr_ok = not (order.get("qr_id") and qr_id and qr_id != order["qr_id"])
    if not amount_ok or not qr_ok:
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"payment_issue": "mismatch", "updated_at": utcnow()}})
        audit("pembayaran_tidak_cocok", f"{order['code']} nominal {amount} vs {order['total']}", XENDIT_ACTOR)
        push_staff("Pembayaran tidak cocok", f"{order['code']}: nominal yang masuk berbeda. Perlu dicek.",
                   f"order-{order['code']}-masalah")
        return jsonify({"ok": True, "ignored": True}), 200

    if order["status"] == "pending":
        mark_order_paid(db, order, "xendit", XENDIT_ACTOR)
    elif order["status"] == "cancelled":
        # Uang masuk setelah pesanan dibatalkan/kedaluwarsa: stok sudah dilepas, jadi ditandai untuk refund manual
        # Xendit mengirim ulang webhook bila balasan terlambat: hanya pengiriman pertama yang menandai dan memberi kabar
        flagged = db.orders.update_one({"_id": order["_id"], "needs_refund": {"$ne": True}},
                                       {"$set": {"needs_refund": True, "updated_at": utcnow()}})
        if flagged.modified_count == 1:
            audit("pembayaran_terlambat", f"{order['code']} dibayar setelah dibatalkan, perlu refund", XENDIT_ACTOR)
            push_staff("Perlu refund", f"{order['code']} dibayar setelah dibatalkan. Kembalikan uang pelanggan.",
                       f"order-{order['code']}-refund")
    return jsonify({"ok": True})