import base64
import json
import re
import time
import urllib.error
import urllib.request

from flask import current_app, request

from tokobiru.core.config import (
    EWALLET_CHANNELS,
    IS_VERCEL,
    PUBLIC_URL,
    XENDIT_API_URL,
    XENDIT_API_VERSION,
    XENDIT_ENABLED,
    XENDIT_SECRET_KEY,
)
from tokobiru.core.security import audit
from tokobiru.services.orders.expiry import cancel_expired_order
from tokobiru.services.orders.stock import release_stock
from tokobiru.services.payments.qris import mark_order_paid


class GatewayError(Exception):
    pass


def xendit_request(method, path, body=None, timeout=5, version=XENDIT_API_VERSION):
    # Pakai urllib bawaan Python supaya tidak menambah dependensi. Key tidak pernah ditulis ke log.
    token = base64.b64encode(f"{XENDIT_SECRET_KEY}:".encode()).decode()
    headers = {"Authorization": "Basic " + token, "Content-Type": "application/json"}
    if version:
        headers["api-version"] = version
    request_ = urllib.request.Request(
        XENDIT_API_URL + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers)
    try:
        with urllib.request.urlopen(request_, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        current_app.logger.error("Xendit %s %s -> HTTP %s %s", method, path, exc.code, detail)
        raise GatewayError(f"HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        current_app.logger.error("Xendit %s %s gagal: %s", method, path, exc)
        raise GatewayError(str(exc)) from exc


def create_xendit_qr(order):
    # reference_id = kode pesanan (unik); nominal dan batas waktu diambil dari pesanan di server
    result = xendit_request("POST", "/qr_codes", {
        "reference_id": order["code"], "type": "DYNAMIC", "currency": "IDR", "amount": order["total"],
        "expires_at": order["expires_at"].replace(microsecond=0).isoformat() + "Z"})
    qr_id, qr_string = result.get("id"), result.get("qr_string")
    if not qr_id or not qr_string:
        raise GatewayError("respons Xendit tidak lengkap")
    return qr_id, qr_string


def create_xendit_ewallet(order, method):
    # API e-wallet Xendit terpisah dari API QR: tanpa header api-version. reference_id = kode pesanan.
    channel = EWALLET_CHANNELS[method]
    # Xendit menuntut https; di balik proxy Vercel host_url bisa terbaca http, jadi dipaksa https bila di Vercel
    base = PUBLIC_URL or request.host_url.rstrip("/")
    if IS_VERCEL and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    props = {"success_redirect_url": f"{base}/?bayar=ok", "failure_redirect_url": f"{base}/?bayar=gagal"}
    if channel == "ID_OVO":
        # OVO tidak memakai tautan: Xendit mengirim notifikasi ke aplikasi OVO sesuai nomor HP
        digits = re.sub(r"\D", "", order["phone"])
        props = {"mobile_number": "+62" + digits.lstrip("0").removeprefix("62")}
    result = xendit_request("POST", "/ewallets/charges", {
        "reference_id": order["code"], "currency": "IDR", "amount": order["total"],
        "checkout_method": "ONE_TIME_PAYMENT", "channel_code": channel, "channel_properties": props},
        version=None)
    charge_id = result.get("id")
    actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
    # DANA memberi tautan web; ShopeePay hanya memberi tautan aplikasi (deeplink); OVO tidak memberi tautan sama sekali
    url = (actions.get("mobile_web_checkout_url") or actions.get("desktop_web_checkout_url")
           or actions.get("mobile_deeplink_checkout_url") or "")
    if not charge_id or (channel != "ID_OVO" and not url):
        given = ",".join(key for key, value in actions.items() if value) or "kosong"
        raise GatewayError(f"respons Xendit tidak lengkap ({channel}, id {'ada' if charge_id else 'tidak ada'}, tautan: {given})")
    return charge_id, url


def drop_unpayable_order(db, order, reason=""):
    # Pesanan dihapus (bukan dibatalkan) supaya percobaan ulang dengan Idempotency-Key yang sama tidak mengembalikan pesanan mati
    if db.orders.delete_one({"_id": order["_id"], "status": "pending"}).deleted_count:
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
        db.order_proofs.delete_one({"_id": order["_id"]})   # foto bukti tidak ditinggalkan tanpa pesanan
        # Alasan dari Xendit (tanpa kunci rahasia) ikut dicatat supaya admin bisa melihatnya di halaman Log
        audit("pesanan_gagal_gateway", f"{order['code']} {reason}".strip()[:240], {"username": "sistem", "role": "-"})


_last_ewallet_sync = {}


def sync_ewallet_status(db, order):
    # Cadangan bila webhook telat/hilang: tanya langsung ke Xendit, paling sering sekali per 3 detik per pesanan
    if order["status"] != "pending" or not order.get("ewallet_id") or not XENDIT_ENABLED:
        return order
    now_ts = time.monotonic()
    if now_ts - _last_ewallet_sync.get(order["_id"], 0) < 3:
        return order
    if len(_last_ewallet_sync) > 500:
        _last_ewallet_sync.clear()
    _last_ewallet_sync[order["_id"]] = now_ts
    try:
        charge = xendit_request("GET", f"/ewallets/charges/{order['ewallet_id']}", timeout=3, version=None)
    except GatewayError:
        return order
    status = str(charge.get("status", "")).upper()
    amount = charge.get("charge_amount")
    if status in XENDIT_PAID_STATUS and isinstance(amount, (int, float)) and amount == order["total"]:
        mark_order_paid(db, order, "xendit", XENDIT_ACTOR)
    elif status == "FAILED":
        cancel_expired_order(db, order, "payment_failed", "pesanan_bayar_gagal")
    else:
        return order
    return db.orders.find_one({"_id": order["_id"]}) or order


XENDIT_PAID_STATUS = ("SUCCEEDED", "COMPLETED")


XENDIT_ACTOR = {"username": "xendit", "role": "-"}