from flask import Blueprint, Response, jsonify
from pymongo.errors import DuplicateKeyError

from tokobiru.core.config import ASSIGNABLE_ROLES, STAFF_ROLES, USERS_LIMIT
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, current_user, roles_required
from tokobiru.core.serializers import serialize
from tokobiru.core.validation import Form, json_body, object_id
from tokobiru.errors import ApiError
from tokobiru.services.orders.expiry import cancel_pending_orders
from tokobiru.services.users import (
    forget_user_devices,
    new_user_doc,
    user_form,
    user_listing,
)

bp = Blueprint("users", __name__)


@bp.get("/api/users")
@roles_required("master")
def users_list():
    docs = get_db().users.find({}, {"image": 0}).sort("created_at", 1).limit(USERS_LIMIT)
    return jsonify({"users": [user_listing(u) for u in docs]})


@bp.get("/api/users/<user_id>/avatar")
@roles_required("master")
def users_avatar(user_id):
    target_id = object_id(user_id, "Pengguna")
    doc = get_db().users.find_one({"_id": target_id}, {"image": 1, "image_type": 1})
    if not doc or not doc.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(doc["image"]), mimetype=doc.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@bp.post("/api/users")
@roles_required("master")
def users_create():
    clean = user_form(json_body(), with_role=True)
    doc = new_user_doc(clean, clean["role"])
    try:
        result = get_db().users.insert_one(doc)
    except DuplicateKeyError:
        raise ApiError("Username atau email sudah terdaftar", 409,
                       {"username": "Username/email sudah dipakai"})
    doc["_id"] = result.inserted_id
    audit("user_buat", f"{clean['username']} ({clean['role']})")
    return jsonify({"user": serialize(doc)}), 201


@bp.patch("/api/users/<user_id>")
@roles_required("master")
def users_update(user_id):
    target_id = object_id(user_id, "Pengguna")
    data = json_body()
    db = get_db()
    actor = current_user()
    target = db.users.find_one({"_id": target_id})
    if not target:
        raise ApiError("Pengguna tidak ditemukan", 404)
    if target["_id"] == actor["_id"] or target["role"] == "master":
        raise ApiError("Akun master tidak dapat diubah dari sini", 403)
    changes = {}
    if "role" in data:
        form = Form(data)
        form.choice("role", "Role", ASSIGNABLE_ROLES)
        changes["role"] = form.done()["role"]
    if "active" in data:
        if not isinstance(data["active"], bool):
            raise ApiError("Status aktif tidak valid", 422)
        changes["active"] = data["active"]
    if not changes:
        raise ApiError("Tidak ada perubahan", 422)
    db.users.update_one({"_id": target_id}, {"$set": changes})
    detail = f"{target['username']}: {changes}"
    if target["role"] in STAFF_ROLES and changes.get("role") == "user":
        forget_user_devices(db, target_id, notifications=True)   # bukan staf lagi: kabar tokonya tidak boleh tersisa
    if changes.get("active") is False:
        forget_user_devices(db, target_id)
        freed = cancel_pending_orders(db, target_id, "account_disabled")
        if freed:
            detail += f" ({freed} pesanan belum dibayar dibatalkan)"
    audit("user_ubah", detail)
    return jsonify({"user": user_listing(db.users.find_one({"_id": target_id}, {"image": 0}))})


@bp.delete("/api/users/<user_id>")
@roles_required("master")
def users_delete(user_id):
    target_id = object_id(user_id, "Pengguna")
    db = get_db()
    target = db.users.find_one({"_id": target_id})
    if not target:
        raise ApiError("Pengguna tidak ditemukan", 404)
    if target["_id"] == current_user()["_id"] or target["role"] == "master":
        raise ApiError("Akun master tidak dapat dihapus", 403)
    # Pesanan yang uangnya mungkin sudah masuk tidak boleh kehilangan pemilik, apalagi foto buktinya: nonaktifkan saja akunnya
    blocking = db.orders.count_documents({"user_id": target_id, "$or": [
        {"status": {"$in": ["paid", "shipped"]}},
        {"status": "pending", "proof_at": {"$ne": None}},
        {"needs_refund": True},
        {"payment_issue": {"$exists": True}}]})
    if blocking:
        raise ApiError(f"Akun ini masih punya {blocking} pesanan yang sedang berjalan atau pembayarannya belum beres, "
                       "jadi belum bisa dihapus. Selesaikan dulu, atau nonaktifkan akunnya saja.", 409)
    freed = cancel_pending_orders(db, target_id, "account_deleted")
    forget_user_devices(db, target_id, notifications=True)
    # Pesanan tetap disimpan untuk pembukuan, tetapi foto bukti (nama, nomor rekening) ikut dihapus bersama akunnya
    order_ids = [order["_id"] for order in db.orders.find({"user_id": target_id}, {"_id": 1})]
    photos = db.order_proofs.delete_many({"_id": {"$in": order_ids}}).deleted_count if order_ids else 0
    db.users.delete_one({"_id": target_id})
    audit("user_hapus", target["username"]
          + (f" ({freed} pesanan belum dibayar dibatalkan)" if freed else "")
          + (f" ({photos} foto bukti dihapus)" if photos else ""))
    return jsonify({"ok": True})