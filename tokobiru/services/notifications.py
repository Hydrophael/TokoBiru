from flask import current_app
import json
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlsplit
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument, UpdateOne
from tokobiru.core.config import PUSH_BUDGET, PUSH_HOST_SUFFIXES, PUSH_MAX_DEVICES_PER_USER, PUSH_MAX_SUBS, PUSH_TIMEOUT, STAFF_ROLES, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT
from tokobiru.core.connection import get_db
from tokobiru.core.util import format_rupiah, utcnow
from tokobiru.errors import ApiError


# --- Notifikasi push (Web Push) untuk staf dan pelanggan ---
try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pywebpush belum terpasang: fitur mati, aplikasi tetap jalan
    webpush = None
    WebPushException = Exception  # type: ignore[misc,assignment]


PUSH_ENABLED = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and webpush)


def require_push_enabled():
    if not PUSH_ENABLED:
        raise ApiError("Notifikasi belum diaktifkan di toko ini.", 503)


def push_endpoint_ok(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 700:
        return False
    try:
        parts = urlsplit(endpoint)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and not parts.username and port in (None, 443)
            and any(host == suffix or host.endswith("." + suffix) for suffix in PUSH_HOST_SUFFIXES))


def push_message(title, body, tag, view="orders"):
    return json.dumps({"title": title, "body": body, "tag": tag, "url": f"/?buka={view}"})


def _push_one(sub, payload):
    """True = terkirim, False = perangkat sudah tidak berlangganan (hapus), None = gagal sementara."""
    if webpush is None:
        return None
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": VAPID_SUBJECT},
                ttl=3600, timeout=PUSH_TIMEOUT)
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return False
        current_app.logger.warning("Push gagal (HTTP %s): %s", status, str(exc)[:200])
    except Exception as exc:
        current_app.logger.warning("Push gagal: %s", str(exc)[:200])
    return None


def deliver_push(db, subs, payload):
    """Kirim ke semua perangkat di `subs`; perangkat yang sudah tidak berlangganan dihapus. Mengembalikan jumlah terkirim."""
    if not subs:
        return 0
    pool = ThreadPoolExecutor(max_workers=min(16, len(subs)))
    futures = [pool.submit(_push_one, sub, payload) for sub in subs]
    try:
        wait(futures, timeout=PUSH_BUDGET)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)   # yang belum selesai ditinggalkan; bukan alasan menahan respons
    results = [future.result() if future.done() and not future.cancelled() and future.exception() is None else None
               for future in futures]
    gone = [sub["_id"] for sub, ok in zip(subs, results) if ok is False]
    if gone:
        db.push_subs.delete_many({"_id": {"$in": gone}})
    return sum(1 for ok in results if ok)


def record_notification(db, user_ids, title, body, tag, view="orders"):
    """Simpan kabar ke pusat notifikasi di dalam aplikasi (lonceng di header). Kabar yang sama (akun + tag) tidak dobel,
    tetapi bila terjadi lagi (mis. bukti transfer diganti) kabar itu diperbarui: isinya diganti, tanda baca dihapus, dan naik ke atas."""
    if not user_ids:
        return
    now = utcnow()
    db.notifications.bulk_write([
        UpdateOne({"user_id": uid, "tag": tag},
                  {"$set": {"title": title, "body": body, "read": False, "created_at": now},
                   "$setOnInsert": {"user_id": uid, "tag": tag, "view": view}}, upsert=True)
        for uid in user_ids], ordered=False)


def push_staff(title, body, tag, view="orders"):
    """Beri kabar ke semua staf (admin/master) di lonceng aplikasi dan, bila aktif, di perangkat mereka. Tidak pernah menggagalkan alur pesanan."""
    try:
        db = get_db()
        staff = [u["_id"] for u in db.users.find({"role": {"$in": list(STAFF_ROLES)}, "active": {"$ne": False}}, {"_id": 1})]
        record_notification(db, staff, title, body, tag, view)
        if not PUSH_ENABLED:
            return
        subs = list(db.push_subs.find({"user_id": {"$in": staff}}).limit(PUSH_MAX_SUBS))
        deliver_push(db, subs, push_message(title, body, tag, view))
    except Exception as exc:
        current_app.logger.warning("Push ke staf gagal: %s", exc)


def push_user(user_id, title, body, tag, view="orders"):
    """Beri kabar ke satu akun (mis. pelanggan pemilik pesanan): di lonceng aplikasi dan, bila aktif, di semua perangkatnya. Tidak pernah menggagalkan alur pesanan."""
    try:
        db = get_db()
        record_notification(db, [user_id], title, body, tag, view)
        if not PUSH_ENABLED:
            return
        subs = list(db.push_subs.find({"user_id": user_id}).limit(PUSH_MAX_DEVICES_PER_USER))
        deliver_push(db, subs, push_message(title, body, tag, view))
    except Exception as exc:
        current_app.logger.warning("Push ke pengguna gagal: %s", exc)


# Kabar untuk pelanggan: status -> (judul, isi)
CUSTOMER_PUSH = {
    "paid": lambda code: ("Pembayaran diterima", f"Pesanan {code} sudah dibayar dan sedang disiapkan."),
    "shipped": lambda code: ("Pesanan dikirim", f"Pesanan {code} sedang diantar. Mohon siap menerima."),
    "cancelled": lambda code: ("Pesanan dibatalkan", f"Pesanan {code} dibatalkan oleh toko. Hubungi toko bila ada pertanyaan."),
}


def customer_push(status, order, refund=False):
    """Kabar untuk pelanggan: sama dengan CUSTOMER_PUSH, tetapi pesanan ambil di toko tidak diantar dan pembatalan yang perlu refund menyebutnya."""
    code = order["code"]
    if status == "shipped" and order.get("shipping_method") == "pickup":
        cash = f" Siapkan uang tunai {format_rupiah(order['total'])}." if order.get("cod") else ""
        return "Pesanan siap diambil", f"Pesanan {code} sudah siap diambil di toko.{cash} Tunjukkan kode pesanan saat mengambil."
    if status == "cancelled" and refund:
        return "Pesanan dibatalkan", f"Pesanan {code} dibatalkan oleh toko. Dana Anda akan dikembalikan; hubungi toko bila ada pertanyaan."
    return CUSTOMER_PUSH[status](code)


def notification_json(doc):
    return {"id": str(doc["_id"]), "title": doc.get("title", ""), "body": doc.get("body", ""),
            "view": doc.get("view", "orders"), "read": bool(doc.get("read")),
            "created_at": doc["created_at"].isoformat() + "Z"}
