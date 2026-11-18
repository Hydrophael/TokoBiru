import hashlib
import hmac
import secrets
from datetime import timedelta

from tokobiru.core.config import (
    EMAIL_ENABLED,
    RESET_CODE_LENGTH,
    RESET_LOCK_MINUTES,
    SECRET_KEY,
)
from tokobiru.errors import ApiError

RESET_FIELDS = {"reset_code_hash": "", "reset_expires": "", "reset_sent_at": ""}


RESET_GUARD_FIELDS = {"reset_failed": "", "reset_locked_until": ""}


def new_reset_code():
    return f"{secrets.randbelow(10 ** RESET_CODE_LENGTH):0{RESET_CODE_LENGTH}d}"


def reset_code_digest(user_id, code):
    # Kode reset disimpan sebagai HMAC, tidak pernah dalam bentuk asli
    return hmac.new(SECRET_KEY.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def lock_reset(db, user, now):
    db.users.update_one({"_id": user["_id"]}, {"$set": {
        "reset_failed": 0, "reset_locked_until": now + timedelta(minutes=RESET_LOCK_MINUTES)}})


def reset_locked_error():
    return ApiError(
        f"Terlalu banyak tebakan kode. Coba lagi dalam {RESET_LOCK_MINUTES} menit.", 429)


def require_email_enabled():
    if not EMAIL_ENABLED:
        raise ApiError("Pemulihan password lewat email belum diaktifkan di toko ini.", 503)