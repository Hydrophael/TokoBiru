import re
import secrets
from datetime import timedelta

from flask import Blueprint, jsonify
from pymongo import ReturnDocument

from tokobiru.core.config import (
    CLOSED_STATUS,
    COD_TTL_HOURS,
    EWALLET_CHANNELS,
    EWALLET_TTL_MINUTES,
    OPEN_ORDERS_LIMIT,
    OPEN_STATUS,
    ORDER_STATUS,
    ORDERS_LIMIT,
    PAYMENT_METHODS,
    PAYMENT_NAME,
    PENDING_TTL_HOURS,
    QRIS_TTL_MINUTES,
    SHIPPING_METHODS,
    STAFF_ROLES,
    XENDIT_ENABLED,
)
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, current_user, login_required, roles_required
from tokobiru.core.serializers import order_json
from tokobiru.core.util import format_rupiah, utcnow
from tokobiru.core.validation import (
    NAME_ERROR,
    PERSON_RE,
    PHONE_ERROR,
    PHONE_RE,
    Form,
    json_body,
    object_id,
)
from tokobiru.errors import ApiError
from tokobiru.services.notifications import (
    CUSTOMER_PUSH,
    customer_push,
    push_staff,
    push_user,
)
from tokobiru.services.orders.cart import parse_cart_items, parse_expected_prices
from tokobiru.services.orders.expiry import settle_overdue, sweep_expired_orders
from tokobiru.services.orders.idempotency import (
    OrderReplay,
    idempotency_key,
    insert_order,
    replayed_order,
)
from tokobiru.services.orders.pending_limit import (
    enforce_pending_limit,
    pending_filter,
    pending_limit,
    pending_limit_error,
)
from tokobiru.services.orders.pricing import shipping_fee_for
from tokobiru.services.orders.status import check_status_change
from tokobiru.services.orders.stock import release_stock, reserve_stock
from tokobiru.services.payments.xendit import (
    GatewayError,
    create_xendit_ewallet,
    create_xendit_qr,
    drop_unpayable_order,
)

bp = Blueprint("orders", __name__)


@bp.get("/api/orders")
@login_required
def orders_list():
    db = get_db()
    sweep_expired_orders(db)
    user = current_user()
    if user["role"] in STAFF_ROLES:
        # Pesanan berjalan selalu tampil; batas jumlah hanya untuk yang sudah selesai atau batal
        open_orders = db.orders.find({"status": {"$in": list(OPEN_STATUS)}}).sort("created_at", -1).limit(OPEN_ORDERS_LIMIT)
        closed_orders = db.orders.find({"status": {"$nin": list(OPEN_STATUS)}}).sort("created_at", -1).limit(ORDERS_LIMIT)
        docs = sorted([*open_orders, *closed_orders], key=lambda o: o["created_at"], reverse=True)
    else:
        # Pesanan yang sudah dihapus pelanggan hanya disembunyikan; toko tetap menyimpannya untuk laporan
        docs = db.orders.find({"user_id": user["_id"], "hidden_by_user": {"$ne": True}}).sort("created_at", -1).limit(ORDERS_LIMIT)
    return jsonify({"orders": [order_json(settle_overdue(db, o), user) for o in docs]})


@bp.post("/api/orders")
@roles_required("user")
def orders_create():
    data = json_body()
    data["phone"] = re.sub(r"[\s.\-]", "", data["phone"]) if isinstance(data.get("phone"), str) else data.get("phone")
    data.setdefault("shipping_method", "delivery")
    data.setdefault("payment_method", PAYMENT_METHODS[0])
    form = Form(data)
    form.choice("shipping_method", "Pengiriman", SHIPPING_METHODS)
    form.choice("payment_method", "Metode pembayaran", PAYMENT_METHODS)
    form.text("phone", "Nomor HP", 8, 16, regex=PHONE_RE, regex_msg=PHONE_ERROR)
    form.text("address", "Alamat pengiriman", 5, 200, required=data["shipping_method"] != "pickup", multiline=True)
    form.text("recipient", "Nama penerima", 2, 50, required=False, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.text("note", "Catatan", 0, 200, required=False, multiline=True)
    clean = form.done()
    if clean["shipping_method"] == "pickup":
        clean["address"] = ""
    wanted = parse_cart_items(data.get("items"))
    expected_prices = parse_expected_prices(data["items"])
    key = idempotency_key()

    db = get_db()
    user = current_user()
    previous = replayed_order(db, user, key, wanted)
    if previous:
        return jsonify({"order": order_json(previous, user), "replayed": True}), 200
    sweep_expired_orders(db)
    enforce_pending_limit(db, user, clean["payment_method"] == "cash")
    reserved, lines = reserve_stock(db, wanted, expected_prices)
    try:
        now = utcnow()
        subtotal = sum(line["subtotal"] for line in lines)
        # Ongkir dan total dihitung di server, angka dari klien tidak dipakai
        fee = shipping_fee_for(subtotal, clean["shipping_method"])
        order = {"user_id": user["_id"], "username": user["username"],
                 "items": lines, "subtotal": subtotal, "shipping_method": clean["shipping_method"],
                 "shipping_fee": fee, "payment_method": clean["payment_method"], "total": subtotal + fee,
                 "phone": clean["phone"], "address": clean["address"], "note": clean["note"],
                 "recipient": clean["recipient"],
                 "cod": clean["payment_method"] == "cash",
                 "status": "pending", "created_at": now, "updated_at": now}
        if clean["payment_method"] == "qris":
            order["expires_at"] = now + timedelta(minutes=QRIS_TTL_MINUTES)
        elif clean["payment_method"] in EWALLET_CHANNELS:
            order["expires_at"] = now + timedelta(minutes=EWALLET_TTL_MINUTES[clean["payment_method"]])
        elif order["cod"]:
            # tunai menunggu toko, bukan pelanggan, jadi batasnya lebih longgar; tanpa batas, pesanan yang ditinggalkan menahan stok selamanya
            order["expires_at"] = now + timedelta(hours=COD_TTL_HOURS)
        else:
            order["expires_at"] = now + timedelta(hours=PENDING_TTL_HOURS)
        if key:
            order["idem_key"] = key
        if clean["payment_method"] == "qris":
            order["pay_token"] = secrets.token_urlsafe(16)
        insert_order(db, order, user, key)
    except OrderReplay as replay:
        release_stock(db, reserved)
        return jsonify({"order": order_json(replay.order, user), "replayed": True}), 200
    except Exception:
        release_stock(db, reserved)
        raise
    # Dua permintaan bersamaan bisa sama-sama lolos pemeriksaan di atas: hitung ulang setelah tersimpan dan batalkan yang berlebih
    pending_now = db.orders.count_documents(pending_filter(user["_id"], order["cod"]))
    if pending_now > pending_limit(order["cod"]):
        drop_unpayable_order(db, order, "melebihi batas pesanan belum dibayar")
        raise pending_limit_error(pending_now - 1, order["cod"])
    if clean["payment_method"] == "qris" and XENDIT_ENABLED:
        try:
            qr_id, qr_string = create_xendit_qr(order)
        except GatewayError as exc:
            drop_unpayable_order(db, order, str(exc))
            raise ApiError("QRIS sedang tidak bisa dibuat. Coba lagi sebentar lagi atau pilih metode lain.", 502)
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"qr_id": qr_id, "qr_string": qr_string}})
        order.update(qr_id=qr_id, qr_string=qr_string)
    if clean["payment_method"] in EWALLET_CHANNELS:
        try:
            charge_id, charge_url = create_xendit_ewallet(order, clean["payment_method"])
        except GatewayError as exc:
            drop_unpayable_order(db, order, str(exc))
            raise ApiError("E-wallet sedang tidak bisa dibuat. Coba lagi sebentar lagi atau pilih metode lain.", 502)
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"ewallet_id": charge_id, "ewallet_url": charge_url}})
        order.update(ewallet_id=charge_id, ewallet_url=charge_url)
    audit("pesanan_buat", f"{order['code']} total {order['total']}")
    push_staff("Pesanan baru", f"{order['code']} · {format_rupiah(order['total'])} · "
                               f"{PAYMENT_NAME.get(order['payment_method'], 'Pesanan')}", f"order-{order['code']}-baru")
    return jsonify({"order": order_json(order, user)}), 201


@bp.patch("/api/orders/<order_id>/status")
@login_required
def orders_status(order_id):
    target_id = object_id(order_id, "Pesanan")
    form = Form(json_body())
    form.choice("status", "Status", ORDER_STATUS)
    new_status = form.done()["status"]
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": target_id})
    if not order or (user["role"] == "user" and order["user_id"] != user["_id"]):
        raise ApiError("Pesanan tidak ditemukan", 404)
    current_status = order["status"]
    check_status_change(user, order, new_status)
    now = utcnow()
    changes = {"status": new_status, "updated_at": now}
    # Uang non-COD sudah masuk bila pesanan dibatalkan dari paid/shipped (termasuk retur setelah dikirim): tandai agar dikembalikan
    refund = new_status == "cancelled" and current_status in ("paid", "shipped") and not order.get("cod")
    if refund:
        changes["needs_refund"] = True
    if new_status == "paid":
        changes["paid_at"] = now
    elif new_status == "completed" and order.get("cod") and current_status == "shipped":
        # COD: uang tunai diterima saat pesanan selesai
        changes.update(paid_at=now, paid_via="cash")
    # Status dicek ulang di filter supaya tidak bentrok dengan perubahan lain
    result = db.orders.update_one({"_id": target_id, "status": current_status}, {"$set": changes})
    if result.modified_count != 1:
        raise ApiError("Status pesanan sudah berubah. Muat ulang data.", 409)
    if new_status == "cancelled":
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
    audit("pesanan_status", f"{order['code']}: {current_status} → {new_status}" + (" (perlu refund)" if refund else ""))
    if refund:
        push_staff("Perlu refund", f"{order['code']} dibatalkan setelah dibayar. Kembalikan uang pelanggan.",
                   f"order-{order['code']}-refund")
    if user["role"] == "user" and new_status == "cancelled":
        push_staff("Pesanan dibatalkan pelanggan", f"{order['code']} · {format_rupiah(order['total'])} dibatalkan oleh pelanggan.",
                   f"order-{order['code']}-batal")
    # Pelanggan dikabari hanya bila yang mengubah status adalah staf toko (bukan dirinya sendiri)
    if user["role"] != "user" and new_status in CUSTOMER_PUSH:
        title, body = customer_push(new_status, order, refund)
        push_user(order["user_id"], title, body, f"my-{order['code']}-{new_status}")
    return jsonify({"order": order_json(db.orders.find_one({"_id": target_id}), user)})


@bp.post("/api/orders/<order_id>/cancel-request")
@roles_required("user")
def order_cancel_request(order_id):
    # Setelah bukti transfer dikirim, uangnya mungkin sudah masuk, jadi pelanggan tidak membatalkan sendiri: ia meminta, staf memutuskan
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"]:
        raise ApiError("Pesanan tidak ditemukan", 404)
    if order["status"] != "pending" or not order.get("proof_at"):
        raise ApiError("Permintaan batal hanya untuk pesanan yang bukti transfernya sudah dikirim dan belum dikonfirmasi. "
                       "Pesanan lain bisa dibatalkan langsung.", 409)
    now = utcnow()
    result = db.orders.update_one(
        {"_id": order["_id"], "status": "pending", "cancel_requested_at": {"$exists": False}},
        {"$set": {"cancel_requested_at": now, "updated_at": now}})
    if result.modified_count == 1:   # permintaan ulang tidak membunyikan notifikasi lagi
        audit("pesanan_minta_batal", order["code"])
        push_staff("Pelanggan minta batal",
                   f"{order['code']} · {format_rupiah(order['total'])}. Bukti transfer sudah diunggah: cek mutasi, lalu batalkan bila setuju.",
                   f"order-{order['code']}-minta-batal")
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


@bp.post("/api/orders/<order_id>/issue-resolved")
@roles_required(*STAFF_ROLES)
def order_issue_resolved(order_id):
    # Admin menandai bahwa refund atau selisih nominal sudah diurus (uangnya sendiri dikembalikan lewat Dashboard Xendit)
    db = get_db()
    user = current_user()
    order = db.orders.find_one_and_update(
        {"_id": object_id(order_id, "Pesanan"), "$or": [{"needs_refund": True}, {"payment_issue": {"$exists": True}}]},
        {"$unset": {"needs_refund": "", "payment_issue": ""}, "$set": {"updated_at": utcnow()}},
        return_document=ReturnDocument.AFTER)
    if not order:
        raise ApiError("Pesanan ini tidak punya masalah pembayaran yang perlu ditangani", 404)
    audit("pembayaran_masalah_selesai", order["code"])
    return jsonify({"order": order_json(order, user)})


@bp.delete("/api/orders/<order_id>")
@roles_required("user")
def order_hide(order_id):
    # Hapus lunak: pesanan hilang dari daftar pelanggan, data toko (omzet, log) tidak berubah
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"]:
        raise ApiError("Pesanan tidak ditemukan", 404)
    if order["status"] not in CLOSED_STATUS:
        raise ApiError("Hanya pesanan selesai atau dibatalkan yang bisa dihapus", 409)
    db.orders.update_one({"_id": order["_id"]}, {"$set": {"hidden_by_user": True, "hidden_at": utcnow()}})
    audit("pesanan_hapus", order["code"])
    return jsonify({"ok": True})


@bp.post("/api/orders/clear-history")
@roles_required("user")
def orders_clear_history():
    db = get_db()
    user = current_user()
    result = db.orders.update_many(
        {"user_id": user["_id"], "status": {"$in": list(CLOSED_STATUS)}, "hidden_by_user": {"$ne": True}},
        {"$set": {"hidden_by_user": True, "hidden_at": utcnow()}})
    if result.modified_count:
        audit("pesanan_bersihkan", f"{result.modified_count} pesanan")
    return jsonify({"removed": result.modified_count})