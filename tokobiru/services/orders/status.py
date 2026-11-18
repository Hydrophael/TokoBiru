from tokobiru.core.config import EWALLET_CHANNELS, TRANSITIONS, USER_TRANSITIONS
from tokobiru.errors import ApiError


def staff_next_statuses(order):
    # COD: uang baru diterima saat barang sampai, jadi tidak lewat "paid" dan boleh dibatalkan saat dikirim
    if order.get("cod"):
        if order["status"] == "pending":
            return {"shipped", "cancelled"}
        if order["status"] == "shipped":
            return {"completed", "cancelled"}
    allowed = set(TRANSITIONS[order["status"]])
    # QRIS dan e-wallet dilunasi oleh Xendit (webhook); staf tidak boleh menandainya dibayar. Hanya transfer bank yang dikonfirmasi manual
    if order["status"] == "pending" and (order.get("payment_method") == "qris" or order.get("payment_method") in EWALLET_CHANNELS):
        allowed.discard("paid")
    return allowed


def check_status_change(user, order, new_status):
    current_status = order["status"]
    if user["role"] == "user":
        # COD: hanya toko yang boleh menyelesaikan, karena penerimaan uang tunai dikonfirmasi toko
        cod_done = order.get("cod") and (current_status, new_status) == ("shipped", "completed")
        if (current_status, new_status) not in USER_TRANSITIONS or cod_done:
            raise ApiError("Anda tidak dapat mengubah pesanan ke status tersebut", 403)
        # Seperti di kebanyakan toko: setelah bukti transfer dikirim, uangnya mungkin sudah masuk, jadi toko yang memutuskan
        if new_status == "cancelled" and order.get("proof_at"):
            raise ApiError("Bukti transfer sudah dikirim, jadi pesanan tidak bisa dibatalkan sendiri. Hubungi toko bila ingin membatalkan.", 409)
    elif new_status not in staff_next_statuses(order):
        raise ApiError(f"Status tidak bisa berubah dari '{current_status}' ke '{new_status}'", 422)