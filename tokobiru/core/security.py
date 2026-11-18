"""TokoBiru - security: header, IP klien, pembatasan percobaan, sesi dan peran, CSRF, dan log audit.

Pemeriksaan sebelum/sesudah request dipasang lewat pasang(app). Nama-nama di sini masih diimpor
ulang oleh app.py supaya kode dan tes lama tetap jalan.
"""
import secrets
from datetime import timedelta
from functools import wraps

from bson import ObjectId
from flask import g, has_request_context, request, session
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from tokobiru.core.config import (
    IS_VERCEL,
    LOCK_MINUTES,
    MAX_FAILED_LOGIN,
    MAX_JSON_BYTES,
    PRODUCT_WRITE_RE,
    PROFILE_WRITE_RE,
    PROOF_WRITE_RE,
    ROLES,
)
from tokobiru.core.connection import get_db
from tokobiru.core.util import utcnow
from tokobiru.core.validation import OID_RE, sanitize
from tokobiru.errors import ApiError

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
# Tanpa script inline; script hanya boleh dari domain sendiri
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def client_ip():
    if not has_request_context():
        return ""
    if IS_VERCEL:
        # Vercel mengisi header ini sendiri; X-Forwarded-For dari klien tidak dipercaya
        ip = request.headers.get("X-Vercel-Forwarded-For", "") or request.headers.get("X-Real-IP", "")
    else:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return sanitize(ip or request.remote_addr or "")[:45]


# --- Pembatasan percobaan (rate limit) per IP, disimpan di MongoDB karena serverless tidak punya memori bersama ---
# bucket: (batas percobaan, jendela waktu dalam detik) per alamat IP
RATE_RULES = {
    "login": (20, 600),
    "register": (5, 3600),
    "forgot": (5, 3600),
    "reset": (15, 600),
}


def _hit(key, window_seconds):
    """Tambah penghitung `key`; mulai jendela baru bila yang lama sudah lewat. Mengembalikan hitungan terbaru."""
    db = get_db()
    now = utcnow()
    for _ in range(2):
        try:
            doc = db.rate_limits.find_one_and_update(
                {"_id": key, "expires": {"$gt": now}},
                {"$inc": {"n": 1}}, return_document=ReturnDocument.AFTER)
            if doc:
                return doc["n"]
            db.rate_limits.replace_one(
                {"_id": key},
                {"_id": key, "n": 1, "expires": now + timedelta(seconds=window_seconds)},
                upsert=True)
            return 1
        except DuplicateKeyError:
            continue
    return 1


def _count(key):
    doc = get_db().rate_limits.find_one({"_id": key, "expires": {"$gt": utcnow()}})
    return doc["n"] if doc else 0


def rate_limit(bucket):
    limit, window = RATE_RULES[bucket]
    if _hit(f"rl:{bucket}:{client_ip() or 'unknown'}", window) > limit:
        raise ApiError("Terlalu banyak percobaan dari jaringan Anda. Coba lagi beberapa menit lagi.", 429)


def proof_read_quota(user, limit):
    """True bila akun ini masih boleh memakai pembacaan AI pada jam ini. Setiap pemanggilan dihitung."""
    return _hit(f"rl:proof:{user['_id']}", 3600) <= limit


# Penguncian login per akun + IP: penebak hanya mengunci dirinya sendiri, pemilik akun dari jaringan lain tetap bisa masuk
def login_locked(user, ip):
    return _count(f"lf:{user['_id']}:{ip}") >= MAX_FAILED_LOGIN


def login_failed(user, ip):
    _hit(f"lf:{user['_id']}:{ip}", LOCK_MINUTES * 60)


def login_ok(user, ip):
    get_db().rate_limits.delete_one({"_id": f"lf:{user['_id']}:{ip}"})


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid and OID_RE.fullmatch(str(uid)):
        user = get_db().users.find_one({"_id": ObjectId(uid)})
        # session_version naik tiap ganti password, jadi sesi lama tidak berlaku lagi
        if user and user.get("active", True) and session.get("sv", 0) == user.get("session_version", 0):
            g.user = user
        else:
            session.clear()
    return g.user


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                raise ApiError("Silakan masuk terlebih dahulu", 401)
            if user["role"] not in roles:
                audit("akses_ditolak", f"{request.method} {request.path}", user)
                raise ApiError("Anda tidak memiliki izin untuk aksi ini", 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def login_required(fn):
    return roles_required(*ROLES)(fn)


def audit(action, detail="", actor=None):
    try:
        user = actor or (current_user() if session.get("uid") else None)
        get_db().logs.insert_one({
            "ts": utcnow(),
            "actor": user["username"] if user else "anonim",
            "role": user["role"] if user else "-",
            "action": action,
            "detail": sanitize(str(detail))[:200],
            "ip": client_ip(),
        })
    except PyMongoError:
        pass


def csrf_token_valid():
    sent = request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf", "")
    return bool(expected) and secrets.compare_digest(sent.encode(), expected.encode())


def guard():
    # Semua request tulis ke API wajib membawa token CSRF dan berbentuk JSON
    if request.path.startswith("/api/") and request.method not in SAFE_METHODS:
        too_big = request.content_length and request.content_length > MAX_JSON_BYTES
        photo_write = (request.method in ("POST", "PUT") and PRODUCT_WRITE_RE.fullmatch(request.path)) or \
                      (request.method == "PATCH" and PROFILE_WRITE_RE.fullmatch(request.path)) or \
                      (request.method == "POST" and PROOF_WRITE_RE.fullmatch(request.path))
        if too_big and not photo_write:
            raise ApiError("Data yang dikirim terlalu besar", 413)
        if not csrf_token_valid():
            raise ApiError("Sesi Anda sudah berakhir atau halaman terlalu lama terbuka. Muat ulang halaman lalu coba lagi.", 403)
        if not request.is_json:
            raise ApiError("Permintaan tidak bisa diproses. Muat ulang halaman lalu coba lagi.", 415)


def secure_headers(resp):
    resp.headers.update(SECURITY_HEADERS)
    if request.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    elif resp.mimetype == "text/html":
        resp.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        resp.headers["Cache-Control"] = "no-cache"
    elif request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def pasang(app):
    """Daftarkan pemeriksaan sebelum dan sesudah tiap request ke aplikasi Flask."""
    app.before_request(guard)
    app.after_request(secure_headers)