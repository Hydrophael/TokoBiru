import re

from flask import request
from pymongo.errors import DuplicateKeyError

from tokobiru.errors import ApiError
from tokobiru.services.orders.codes import ORDER_CODE_ATTEMPTS, new_order_code

IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{8,64}")


class OrderReplay(Exception):
    def __init__(self, order):
        super().__init__("order replay")
        self.order = order


def idempotency_key():
    # Kunci yang sama saat request diulang mencegah pesanan ganda bila jaringan putus
    raw = request.headers.get("Idempotency-Key", "").strip()
    if not raw:
        return None
    if not IDEMPOTENCY_KEY_RE.fullmatch(raw):
        raise ApiError("Permintaan tidak valid. Muat ulang halaman lalu coba lagi.", 422)
    return raw


def replayed_order(db, user, key, wanted):
    if key is None:
        return None
    order = db.orders.find_one({"user_id": user["_id"], "idem_key": key})
    if order is None:
        return None
    if {item["product_id"]: item["qty"] for item in order["items"]} != wanted:
        raise ApiError("Isi keranjang berubah saat pesanan dikirim. Muat ulang halaman lalu coba lagi.", 422)
    return order


def insert_order(db, order, user, key):
    for _ in range(ORDER_CODE_ATTEMPTS):
        order["code"] = new_order_code()
        try:
            db.orders.insert_one(order)
            return order
        except DuplicateKeyError:
            order.pop("_id", None)
            if key is not None:
                existing = db.orders.find_one({"user_id": user["_id"], "idem_key": key})
                if existing:
                    raise OrderReplay(existing)
    raise ApiError("Gagal membuat kode pesanan. Coba lagi.", 503)