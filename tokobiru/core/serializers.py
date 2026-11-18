"""TokoBiru - mengubah dokumen MongoDB menjadi JSON untuk klien (menyembunyikan field internal).

Nama-nama di sini masih diimpor ulang oleh app.py supaya kode dan tes lama tetap jalan.
"""
from datetime import datetime

from bson import ObjectId

from tokobiru.core.config import STAFF_ROLES, XENDIT_SIMULATE_SCAN

HIDDEN_FIELDS = ("password_hash", "failed", "locked_until", "idem_key", "session_version", "pay_token", "qr_id", "qr_string",
                 "ewallet_id", "ewallet_url",
                 "reset_code_hash", "reset_expires", "reset_sent_at", "reset_failed", "reset_locked_until",
                 "image", "image_type", "image_v",
                 "addresses", "hidden_by_user", "hidden_at", "proof_remind_sent")


def serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    if isinstance(value, dict):
        return serialize(value)
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    return value


def serialize(doc):
    if doc is None:
        return None
    out = {}
    for key, value in doc.items():
        if key in HIDDEN_FIELDS:
            continue
        if key == "_id":
            out["id"] = str(value)
        else:
            out[key] = serialize_value(value)
    return out


def order_json(order, user=None):
    # Tautan bayar dan kode QRIS hanya untuk pemilik, selama pesanan masih menunggu bayar
    out = serialize(order)
    owner_pending = bool(order.get("status") == "pending"
                         and user and user["role"] == "user" and user["_id"] == order.get("user_id"))
    if owner_pending and order.get("pay_token"):
        out["pay_path"] = f"/pay/{order['pay_token']}"
    if owner_pending and order.get("qr_string") and not XENDIT_SIMULATE_SCAN:
        out["qr_string"] = order["qr_string"]
    if owner_pending and order.get("ewallet_url"):
        out["ewallet_url"] = order["ewallet_url"]
    # Penanda masalah uang (refund, nominal tidak cocok) hanya untuk admin
    if not (user and user["role"] in STAFF_ROLES):
        out.pop("needs_refund", None)
        out.pop("payment_issue", None)
        out.pop("proof_check", None)   # hasil baca bukti hanya untuk staf
    return out


def address_json(item):
    return {"id": item["id"], "label": item["label"], "recipient": item["recipient"],
            "phone": item["phone"], "address": item["address"], "main": bool(item.get("main"))}