import hmac
from datetime import datetime, timedelta, timezone
from email.utils import make_msgid
from flask import Blueprint, Response, current_app, g, has_request_context, jsonify, request, send_from_directory, session
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument, UpdateOne
from tokobiru.core import passwords
from tokobiru.core.config import MAX_RESET_ATTEMPTS, RESET_CODE_LENGTH, RESET_CODE_MINUTES, RESET_COOLDOWN_SECONDS
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, rate_limit
from tokobiru.core.validation import EMAIL_ERROR, EMAIL_RE, Form, RESET_CODE_ERROR, RESET_CODE_RE, RESET_FAILED_ERROR, json_body
from tokobiru.core.util import utcnow
from tokobiru.errors import ApiError
from tokobiru.services.mailer import load_email_logo, reset_email_html, reset_email_text, send_email
from tokobiru.services.password_reset import RESET_FIELDS, RESET_GUARD_FIELDS, lock_reset, new_reset_code, require_email_enabled, reset_code_digest, reset_locked_error

bp = Blueprint("password_reset", __name__)


@bp.post("/api/auth/forgot")
def auth_forgot():
    rate_limit("forgot")
    require_email_enabled()
    form = Form(json_body())
    form.text("email", "Email", 5, 120, lower=True, regex=EMAIL_RE, regex_msg=EMAIL_ERROR)
    email = form.done()["email"]
    db = get_db()
    user = db.users.find_one({"email": email})
    now = utcnow()
    sent_at = user.get("reset_sent_at") if user else None
    cooling_down = bool(sent_at) and (now - sent_at).total_seconds() < RESET_COOLDOWN_SECONDS
    if user and user.get("active", True) and not cooling_down:
        code = new_reset_code()
        db.users.update_one({"_id": user["_id"]}, {"$set": {
            "reset_code_hash": reset_code_digest(user["_id"], code),
            "reset_expires": now + timedelta(minutes=RESET_CODE_MINUTES),
            "reset_sent_at": now}})
        try:
            name = user.get("name") or "pelanggan"
            logo = load_email_logo()
            logo_cid = make_msgid(domain="tokobiru.local")[1:-1] if logo else None
            send_email(user["email"], "Kode reset password TokoBiru",
                       reset_email_text(name, code), html=reset_email_html(name, code, logo_cid),
                       inline_images={logo_cid: logo} if logo else None)
        except Exception as exc:
            current_app.logger.error("Gagal mengirim email reset password: %s", exc)
            db.users.update_one({"_id": user["_id"]}, {"$unset": RESET_FIELDS})
        else:
            audit("reset_minta", "kode dikirim ke email", user)
    return jsonify({"ok": True, "retry_after": RESET_COOLDOWN_SECONDS, "expires_minutes": RESET_CODE_MINUTES})


@bp.post("/api/auth/reset")
def auth_reset():
    rate_limit("reset")
    require_email_enabled()
    form = Form(json_body())
    form.text("email", "Email", 5, 120, lower=True, regex=EMAIL_RE, regex_msg=EMAIL_ERROR)
    form.text("code", "Kode", RESET_CODE_LENGTH, RESET_CODE_LENGTH, regex=RESET_CODE_RE, regex_msg=RESET_CODE_ERROR)
    form.password("new_password", "Password baru")
    clean = form.done()
    db = get_db()
    user = db.users.find_one({"email": clean["email"]})
    now = utcnow()
    pending = bool(user and user.get("active", True) and user.get("reset_code_hash")
                   and user.get("reset_expires") and user["reset_expires"] > now)
    if pending:
        attempt = db.users.find_one_and_update(
            {"_id": user["_id"], "reset_expires": {"$gt": now}, "reset_code_hash": {"$exists": True},
             "$or": [{"reset_locked_until": {"$exists": False}}, {"reset_locked_until": None},
                     {"reset_locked_until": {"$lte": now}}]},
            {"$inc": {"reset_failed": 1}},
            return_document=ReturnDocument.AFTER)
        locked_until = user.get("reset_locked_until")
        if attempt is None:
            if locked_until and locked_until > now:
                raise reset_locked_error()
            raise ApiError(RESET_FAILED_ERROR, 422, {"code": "Kode salah atau sudah kedaluwarsa"})
        tries = attempt.get("reset_failed", 1)
        if tries > MAX_RESET_ATTEMPTS:
            lock_reset(db, user, now)
            raise reset_locked_error()
        result = db.users.update_one(
            {"_id": user["_id"], "reset_code_hash": reset_code_digest(user["_id"], clean["code"])},
            {"$set": {"password_hash": passwords.hash_password(clean["new_password"]),
                      "failed": 0, "locked_until": None},
             "$inc": {"session_version": 1},
             "$unset": {**RESET_FIELDS, **RESET_GUARD_FIELDS}})
        if result.modified_count == 1:
            audit("password_reset", "lewat kode email", user)
            db.rate_limits.delete_many({"_id": {"$regex": "^lf:" + str(user["_id"]) + ":"}})
            return jsonify({"ok": True})
        if tries >= MAX_RESET_ATTEMPTS:
            lock_reset(db, user, now)
            audit("reset_gagal", "kode salah, reset dikunci sementara", user)
            raise reset_locked_error()
        audit("reset_gagal", "kode salah", user)
    raise ApiError(RESET_FAILED_ERROR, 422, {"code": "Kode salah atau sudah kedaluwarsa"})


@bp.post("/api/auth/reset/check")
def auth_reset_check():
    rate_limit("reset")
    require_email_enabled()
    form = Form(json_body())
    form.text("email", "Email", 5, 120, lower=True, regex=EMAIL_RE, regex_msg=EMAIL_ERROR)
    form.text("code", "Kode", RESET_CODE_LENGTH, RESET_CODE_LENGTH, regex=RESET_CODE_RE, regex_msg=RESET_CODE_ERROR)
    clean = form.done()
    db = get_db()
    user = db.users.find_one({"email": clean["email"]})
    now = utcnow()
    pending = bool(user and user.get("active", True) and user.get("reset_code_hash")
                   and user.get("reset_expires") and user["reset_expires"] > now)
    if pending:
        attempt = db.users.find_one_and_update(
            {"_id": user["_id"], "reset_expires": {"$gt": now}, "reset_code_hash": {"$exists": True},
             "$or": [{"reset_locked_until": {"$exists": False}}, {"reset_locked_until": None},
                     {"reset_locked_until": {"$lte": now}}]},
            {"$inc": {"reset_failed": 1}},
            return_document=ReturnDocument.AFTER)
        locked_until = user.get("reset_locked_until")
        if attempt is None:
            if locked_until and locked_until > now:
                raise reset_locked_error()
            raise ApiError(RESET_FAILED_ERROR, 422, {"code": "Kode salah atau sudah kedaluwarsa"})
        tries = attempt.get("reset_failed", 1)
        if tries > MAX_RESET_ATTEMPTS:
            lock_reset(db, user, now)
            raise reset_locked_error()
        if hmac.compare_digest(str(attempt.get("reset_code_hash", "")), reset_code_digest(user["_id"], clean["code"])):
            db.users.update_one({"_id": user["_id"], "reset_failed": {"$gt": 0}}, {"$inc": {"reset_failed": -1}})
            return jsonify({"ok": True})
        if tries >= MAX_RESET_ATTEMPTS:
            lock_reset(db, user, now)
            audit("reset_gagal", "kode salah, reset dikunci sementara", user)
            raise reset_locked_error()
        audit("reset_gagal", "kode salah", user)
    raise ApiError(RESET_FAILED_ERROR, 422, {"code": "Kode salah atau sudah kedaluwarsa"})
