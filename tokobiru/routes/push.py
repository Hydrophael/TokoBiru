import hashlib

from flask import Blueprint, jsonify

from tokobiru.core.config import PUSH_KEY_RE, PUSH_MAX_DEVICES_PER_USER
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, current_user, login_required
from tokobiru.core.util import utcnow
from tokobiru.core.validation import json_body, object_id
from tokobiru.errors import ApiError
from tokobiru.services.notifications import (
    notification_json,
    push_endpoint_ok,
    require_push_enabled,
)

bp = Blueprint("push", __name__)


@bp.post("/api/push/subscribe")
@login_required
def push_subscribe():
    require_push_enabled()
    sub = json_body().get("subscription")
    keys = sub.get("keys") if isinstance(sub, dict) else None
    keys = keys if isinstance(keys, dict) else {}
    endpoint, p256dh, auth = (sub or {}).get("endpoint") if isinstance(sub, dict) else None, keys.get("p256dh"), keys.get("auth")
    if not isinstance(endpoint, str) or not push_endpoint_ok(endpoint) or not all(isinstance(k, str) and PUSH_KEY_RE.fullmatch(k) for k in (p256dh, auth)):
        raise ApiError("Notifikasi tidak bisa diaktifkan di perangkat ini.", 422)
    db = get_db()
    user = current_user()
    sub_id = hashlib.sha256(endpoint.encode()).hexdigest()
    # Satu perangkat milik satu akun: bila akun lain masuk di perangkat yang sama, kepemilikannya berpindah
    db.push_subs.replace_one({"_id": sub_id}, {"_id": sub_id, "user_id": user["_id"], "endpoint": endpoint,
                                               "p256dh": p256dh, "auth": auth, "created_at": utcnow()}, upsert=True)
    mine = list(db.push_subs.find({"user_id": user["_id"]}, {"_id": 1}).sort("created_at", -1))
    if len(mine) > PUSH_MAX_DEVICES_PER_USER:
        db.push_subs.delete_many({"_id": {"$in": [doc["_id"] for doc in mine[PUSH_MAX_DEVICES_PER_USER:]]}})
    audit("push_aktif", "notifikasi diaktifkan di satu perangkat")
    return jsonify({"ok": True})


@bp.post("/api/push/unsubscribe")
@login_required
def push_unsubscribe():
    endpoint = json_body().get("endpoint")
    if isinstance(endpoint, str) and len(endpoint) <= 700:
        sub_id = hashlib.sha256(endpoint.encode()).hexdigest()
        get_db().push_subs.delete_one({"_id": sub_id, "user_id": current_user()["_id"]})
    return jsonify({"ok": True})


@bp.get("/api/notifications")
@login_required
def notifications_list():
    db = get_db()
    uid = current_user()["_id"]
    docs = list(db.notifications.find({"user_id": uid}).sort("created_at", -1).limit(30))
    unread = db.notifications.count_documents({"user_id": uid, "read": False})
    resp = jsonify({"items": [notification_json(doc) for doc in docs], "unread": unread})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/api/notifications/read")
@login_required
def notifications_read():
    body = json_body()
    db = get_db()
    uid = current_user()["_id"]
    if body.get("all") is True:
        db.notifications.update_many({"user_id": uid, "read": False}, {"$set": {"read": True}})
    else:
        ids = body.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > 50:
            raise ApiError("Notifikasi tidak dapat diproses. Muat ulang halaman lalu coba lagi.", 400)
        db.notifications.update_many({"_id": {"$in": [object_id(item, "Notifikasi") for item in ids]}, "user_id": uid},
                                     {"$set": {"read": True}})
    return jsonify({"ok": True})