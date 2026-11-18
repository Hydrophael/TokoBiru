import secrets
from datetime import datetime, timedelta, timezone
from flask import Blueprint, Response, current_app, g, has_request_context, jsonify, request, send_from_directory, session
from tokobiru.core.config import LOCK_MINUTES, MAX_FAILED_LOGIN
from tokobiru.errors import ApiError


def start_session(user):
    session.clear()
    session.permanent = True
    session["uid"] = str(user["_id"])
    session["sv"] = user.get("session_version", 0)
    session["csrf"] = secrets.token_urlsafe(32)


def record_failed_login(db, user, now):
    failed = user.get("failed", 0) + 1
    changes = {"failed": failed}
    if failed >= MAX_FAILED_LOGIN:
        changes = {"failed": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}
    db.users.update_one({"_id": user["_id"]}, {"$set": changes})


def account_locked_error():
    return ApiError(
        f"Akun dikunci sementara karena terlalu banyak percobaan. Coba lagi dalam {LOCK_MINUTES} menit.", 429)
