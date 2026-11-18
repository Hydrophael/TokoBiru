import time
from datetime import timedelta

from flask import current_app
from pymongo.errors import PyMongoError

from tokobiru.core.config import (
    COD_REMIND_HOURS,
    EXPIRE_BATCH,
    EXPIRE_SWEEP_SECONDS,
    PENDING_TTL_HOURS,
    PROOF_REMIND_HOURS,
    WIB_OFFSET,
)
from tokobiru.core.security import audit
from tokobiru.core.util import format_rupiah, utcnow
from tokobiru.services.notifications import push_staff, record_notification
from tokobiru.services.orders.stock import release_stock

_last_sweep = None


def is_overdue(order):
    # Transfer yang sudah ada buktinya tidak kedaluwarsa sendiri: uangnya mungkin sudah masuk, jadi stafflah yang memutuskan
    expires = order.get("expires_at")
    return bool(order.get("status") == "pending" and expires and expires <= utcnow() and not order.get("proof_at"))


def cancel_expired_order(db, order, reason="expired", audit_action="pesanan_kedaluwarsa"):
    # Atomik: hanya pesanan yang masih pending yang dibatalkan, stok dikembalikan sekali saja
    query = {"_id": order["_id"], "status": "pending"}
    if reason == "expired":
        query["proof_at"] = None   # bukti bisa saja baru diunggah setelah pesanan dibaca: jangan dibatalkan
    result = db.orders.update_one(
        query,
        {"$set": {"status": "cancelled", "cancel_reason": reason, "updated_at": utcnow()}})
    if result.modified_count != 1:
        return False
    release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
    audit(audit_action, order["code"], {"username": "sistem", "role": "-"})
    why = ("karena pembayaran gagal atau ditolak" if reason == "payment_failed" else "karena melewati batas waktu bayar")
    try:
        record_notification(db, [order["user_id"]], "Pesanan dibatalkan", f"Pesanan {order['code']} dibatalkan otomatis {why}.",
                            f"my-{order['code']}-batal")
    except PyMongoError as exc:
        current_app.logger.warning("Kabar pembatalan otomatis gagal disimpan: %s", exc)
    return True


def settle_overdue(db, order):
    # Batas bayar dicek per pesanan agar hitung mundur di layar tepat, tidak menunggu penyapuan berkala
    if order and is_overdue(order):
        cancel_expired_order(db, order)
        return db.orders.find_one({"_id": order["_id"]}) or order
    return order


def remind_cod_orders(db, now):
    # Pesanan tunai yang hampir kedaluwarsa: staf diingatkan sekali supaya sempat memproses atau membatalkannya sendiri
    due = db.orders.find({"status": "pending", "cod": True, "remind_sent": {"$ne": True},
                          "expires_at": {"$gt": now, "$lte": now + timedelta(hours=COD_REMIND_HOURS)}}).limit(EXPIRE_BATCH)
    for order in list(due):
        claimed = db.orders.update_one({"_id": order["_id"], "status": "pending", "remind_sent": {"$ne": True}},
                                       {"$set": {"remind_sent": True}})
        if claimed.modified_count != 1:
            continue   # permintaan lain sudah mengingatkan
        deadline = (order["expires_at"] + WIB_OFFSET).strftime("%d/%m %H:%M")
        push_staff("Pesanan tunai belum diproses",
                   f"{order['code']} · {format_rupiah(order['total'])} akan dibatalkan otomatis {deadline} WIB. Proses atau batalkan sebelum itu.",
                   f"order-{order['code']}-ingat")


def remind_proof_orders(db, now):
    # Transfer yang sudah ada buktinya tidak kedaluwarsa sendiri, jadi stok dan jatah pesanan pelanggan tertahan sampai staf bertindak.
    # Staf diingatkan sekali setelah PROOF_REMIND_HOURS jam supaya pesanan tidak terlupakan.
    due = db.orders.find({"status": "pending", "proof_remind_sent": {"$ne": True},
                          "proof_at": {"$lte": now - timedelta(hours=PROOF_REMIND_HOURS)}}).limit(EXPIRE_BATCH)
    for order in list(due):
        claimed = db.orders.update_one({"_id": order["_id"], "status": "pending", "proof_remind_sent": {"$ne": True}},
                                       {"$set": {"proof_remind_sent": True}})
        if claimed.modified_count != 1:
            continue   # permintaan lain sudah mengingatkan
        push_staff("Bukti transfer belum dicek",
                   f"{order['code']} · {format_rupiah(order['total'])}: bukti sudah diunggah lebih dari {PROOF_REMIND_HOURS} jam. "
                   "Cek mutasi, lalu konfirmasi pembayaran atau batalkan.",
                   f"order-{order['code']}-ingat-bukti")


def sweep_expired_orders(db, force=False):
    # Dijalankan malas saat ada request, karena serverless tidak punya proses latar belakang
    global _last_sweep
    now_ts = time.monotonic()
    if not force and _last_sweep is not None and now_ts - _last_sweep < EXPIRE_SWEEP_SECONDS:
        return 0
    _last_sweep = now_ts

    cancelled = 0
    try:
        now = utcnow()
        cutoff = now - timedelta(hours=PENDING_TTL_HOURS)
        # Batas bayar tiap pesanan ada di expires_at; created_at hanya cadangan untuk data lama
        stale = list(db.orders.find({"status": "pending", "proof_at": None,   # ada bukti transfer: tidak dibatalkan otomatis
                                     "$or": [{"expires_at": {"$lte": now}},
                                             {"expires_at": {"$exists": False}, "created_at": {"$lt": cutoff}}]}
                                    ).limit(EXPIRE_BATCH))
        for order in stale:
            if cancel_expired_order(db, order):
                cancelled += 1
        remind_cod_orders(db, now)
        remind_proof_orders(db, now)
    except PyMongoError as exc:
        current_app.logger.error("Penyapuan pesanan kedaluwarsa gagal: %s", exc)
    return cancelled


def cancel_pending_orders(db, user_id, reason):
    cancelled = 0
    for order in db.orders.find({"user_id": user_id, "status": "pending"}):
        changes = {"status": "cancelled", "cancel_reason": reason, "updated_at": utcnow()}
        has_proof = bool(order.get("proof_at"))
        if has_proof:
            changes["payment_issue"] = "proof_cancelled"   # bukti sudah dikirim: uangnya mungkin sudah masuk
        result = db.orders.update_one({"_id": order["_id"], "status": "pending"}, {"$set": changes})
        if result.modified_count != 1:
            continue
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
        cancelled += 1
        if has_proof:
            push_staff("Cek bukti transfer", f"{order['code']} dibatalkan karena akun pelanggan diubah, tetapi bukti transfer sudah diunggah. Cek mutasi.",
                       f"order-{order['code']}-masalah")
    return cancelled