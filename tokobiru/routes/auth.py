import hashlib
import secrets
from flask import Blueprint, Response, current_app, g, has_request_context, jsonify, request, send_from_directory, session
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from tokobiru.core import passwords
from tokobiru.core.config import DUMMY_QRIS, EMAIL_ENABLED, EWALLET_TTL_MINUTES, FREE_SHIPPING_MIN, LOCK_MINUTES, PAY_INFO, PROOF_READER_ENABLED, PROOF_RETENTION_DAYS, QRIS_ENABLED, QRIS_TTL_MINUTES, SHIPPING_FEE, XENDIT_ENABLED
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, client_ip, current_user, login_failed, login_locked, login_ok, login_required, rate_limit
from tokobiru.core.validation import Form, NAME_ERROR, PERSON_RE, json_body
from tokobiru.core.util import utcnow
from tokobiru.errors import ApiError
from tokobiru.services.products import split_image
from tokobiru.services.sessions import account_locked_error, record_failed_login, start_session
from tokobiru.services.users import new_user_doc, public_user, user_form

bp = Blueprint("auth", __name__)


@bp.get("/api/auth/me")
def auth_me():
    user = current_user()
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"user": public_user(user), "csrf": session["csrf"], "pay_info": PAY_INFO,
                    "dummy_qris": DUMMY_QRIS, "qris_enabled": QRIS_ENABLED, "ewallet_enabled": XENDIT_ENABLED, "qris_minutes": QRIS_TTL_MINUTES,
                    "ewallet_minutes": EWALLET_TTL_MINUTES, "proof_reader": PROOF_READER_ENABLED, "proof_retention_days": PROOF_RETENTION_DAYS,
                    "server_time": utcnow().isoformat() + "Z", "reset_enabled": EMAIL_ENABLED,
                    "shipping": {"fee": SHIPPING_FEE, "free_min": FREE_SHIPPING_MIN}})


@bp.post("/api/auth/register")
def auth_register():
    rate_limit("register")
    clean = user_form(json_body())
    db = get_db()
    doc = new_user_doc(clean, "user")
    try:
        result = db.users.insert_one(doc)
    except DuplicateKeyError:
        taken = db.users.find_one({"username": clean["username"]})
        field = "username" if taken else "email"
        raise ApiError("Data sudah dipakai", 409, {field: f"{field.capitalize()} sudah terdaftar"})
    doc["_id"] = result.inserted_id
    start_session(doc)
    audit("register", f"akun baru {clean['username']}", doc)
    return jsonify({"user": public_user(doc), "csrf": session["csrf"]}), 201


@bp.post("/api/auth/login")
def auth_login():
    rate_limit("login")
    form = Form(json_body())
    form.text("identifier", "Username/email", 1, 120, lower=True)
    form.password("password", "Password", enforce_policy=False)
    clean = form.done()
    identifier = clean["identifier"]
    db = get_db()
    ip = client_ip() or "unknown"
    user = db.users.find_one({"$or": [{"username": identifier}, {"email": identifier}]})
    now = utcnow()
    if user and login_locked(user, ip):
        raise account_locked_error()
    stored_hash = user["password_hash"] if user else passwords.DUMMY_HASH
    password_ok = passwords.check_password(stored_hash, clean["password"])
    if user is None or not password_ok:
        if user:
            login_failed(user, ip)
        audit("login_gagal", f"identifier={identifier[:40]}" if user else "akun tidak dikenal")
        raise ApiError("Username/email atau password salah", 401)
    if not user.get("active", True):
        raise ApiError("Akun Anda dinonaktifkan. Silakan hubungi pengelola toko.", 403)
    login_ok(user, ip)
    db.users.update_one({"_id": user["_id"]}, {"$set": {"failed": 0, "last_login": now}})
    start_session(user)
    audit("login", "berhasil masuk", user)
    return jsonify({"user": public_user(user), "csrf": session["csrf"]})


@bp.post("/api/auth/logout")
def auth_logout():
    if session.get("uid"):
        endpoint = (request.get_json(silent=True) or {}).get("endpoint")
        try:
            user = current_user()
            if user and isinstance(endpoint, str) and len(endpoint) <= 700:
                # Perangkat ini dilepas dari akun supaya akun lain di perangkat yang sama tidak menerima kabar toko
                get_db().push_subs.delete_one({"_id": hashlib.sha256(endpoint.encode()).hexdigest(), "user_id": user["_id"]})
        except PyMongoError as exc:
            current_app.logger.warning("Langganan push gagal dilepas saat keluar: %s", exc)
        audit("logout", "")
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"ok": True, "csrf": session["csrf"]})


@bp.patch("/api/auth/profile")
@login_required
def auth_profile():
    form = Form(json_body())
    form.text("name", "Nama lengkap", 2, 50, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.image("image", "Foto profil")
    clean = form.done()
    db = get_db()
    user = current_user()

    changes = {}
    notes = []
    if clean["name"] != user["name"]:
        changes["name"] = clean["name"]
        notes.append(f"nama diubah ({user['name']} → {clean['name']})")
    image_set, image_unset = split_image(clean)
    update = {}
    if image_set:
        changes.update(image_set)
        notes.append("foto diganti")
    elif image_unset and user.get("image"):
        update["$unset"] = image_unset
        notes.append("foto dihapus")
    if changes:
        update["$set"] = changes
    if update:
        db.users.update_one({"_id": user["_id"]}, update)
        audit("profil_ubah", ", ".join(notes))
        user = db.users.find_one({"_id": user["_id"]})
    return jsonify({"ok": True, "user": public_user(user)})


@bp.get("/api/auth/avatar")
@login_required
def auth_avatar():
    user = current_user()
    if not user.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(user["image"]), mimetype=user.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@bp.patch("/api/auth/password")
@login_required
def auth_password():
    form = Form(json_body())
    form.password("current_password", "Password lama", enforce_policy=False)
    form.password("new_password", "Password baru")
    clean = form.done()
    db = get_db()
    user = current_user()
    now = utcnow()
    if user.get("locked_until") and user["locked_until"] > now:
        raise ApiError(f"Ganti password dikunci sementara karena terlalu banyak percobaan. Coba lagi dalam {LOCK_MINUTES} menit.", 429)
    if not passwords.check_password(user["password_hash"], clean["current_password"]):
        record_failed_login(db, user, now)
        login_failed(user, client_ip())
        audit("password_gagal", "password lama salah")
        raise ApiError("Password lama salah", 422, {"current_password": "Password lama salah"})
    if clean["new_password"] == clean["current_password"]:
        message = "Password baru harus berbeda dari yang lama"
        raise ApiError(message, 422, {"new_password": message})
    db.users.update_one({"_id": user["_id"]}, {
        "$set": {"password_hash": passwords.hash_password(clean["new_password"]),
                 "failed": 0, "locked_until": None},
        "$inc": {"session_version": 1}})
    session["sv"] = db.users.find_one({"_id": user["_id"]}).get("session_version", 1)
    audit("password_ubah", "sesi di perangkat lain dikeluarkan")
    return jsonify({"ok": True})
