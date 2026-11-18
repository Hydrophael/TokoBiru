from tokobiru.core.config import MAX_PENDING_COD, MAX_PENDING_ORDERS
from tokobiru.errors import ApiError


def pending_filter(user_id, cod):
    # Pesanan tunai menunggu toko, yang lain menunggu pembayaran pelanggan: dua batas terpisah
    return {"user_id": user_id, "status": "pending", "cod": True if cod else {"$ne": True}}


def pending_limit(cod):
    return MAX_PENDING_COD if cod else MAX_PENDING_ORDERS


def enforce_pending_limit(db, user, cod=False):
    # Stok ditahan sejak pesanan dibuat, jadi pesanan yang belum selesai dibatasi per pelanggan
    pending = db.orders.count_documents(pending_filter(user["_id"], cod))
    if pending >= pending_limit(cod):
        raise pending_limit_error(pending, cod)


def pending_limit_error(pending, cod=False):
    if cod:
        return ApiError(
            f"Anda masih punya {pending} pesanan tunai yang menunggu diproses toko. "
            "Tunggu sampai diproses, atau batalkan salah satunya di menu Pesanan sebelum membuat yang baru.",
            429,
        )
    return ApiError(
        f"Anda masih punya {pending} pesanan yang belum dibayar. "
        "Bayar atau batalkan salah satunya di menu Pesanan sebelum membuat yang baru.",
        429,
    )
