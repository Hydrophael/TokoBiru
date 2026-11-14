"""
TokoBiru - Aplikasi Retail Multi-Role (user / admin / master)
=============================================================
Stack    : Flask + MongoDB (pymongo), frontend di templates/ dan static/
Keamanan : sesi cookie bertanda tangan (HttpOnly, SameSite), hash password,
           token CSRF, CSP, RBAC (user < admin < master), validasi dan sanitasi
           input, anti NoSQL-injection, pembatasan login, log audit.

Jalankan lokal
    pip install -r requirements.txt
    python app.py create-master      # buat akun master pertama (sekali saja)
    python app.py seed-demo          # opsional: akun demo tiap role + contoh produk
    python app.py
    (opsional: salin .env.example menjadi .env; dimuat otomatis bila python-dotenv terpasang)

Environment variable
    MONGO_URI     alamat MongoDB (wajib di Vercel; lokal default mongodb://localhost:27017)
    MONGO_DB      nama database (default: tokobiru)
    SECRET_KEY    string acak panjang (wajib di Vercel)
    MASTER_USERNAME / MASTER_EMAIL / MASTER_PASSWORD / MASTER_NAME
                  opsional: membuat akun master otomatis bila belum ada master
    PAY_INFO      opsional: instruksi pembayaran yang tampil di pesanan pelanggan
    PENDING_TTL_HOURS  opsional: batas jam bayar sebelum pesanan dibatalkan otomatis (default 24)
    MAX_PENDING_ORDERS opsional: jumlah pesanan belum dibayar yang boleh dimiliki satu pelanggan (default 3)
    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM
                  opsional: server email untuk kode reset password (port 587 STARTTLS, atau 465 SSL).
                  Tanpa SMTP_HOST dan pengirim (SMTP_FROM atau SMTP_USER), tombol "Lupa password" tidak tampil.
    Variabel yang dibiarkan kosong diperlakukan sama seperti tidak diisi (memakai nilai bawaan).
"""
import base64
import getpass
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from functools import wraps
from html import escape as html_escape

from bson import ObjectId
from flask import (Flask, Response, g, has_request_context, jsonify, request,
                   send_from_directory, session)
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

# --------------------------------------------------------------------------- #
# Konfigurasi
# --------------------------------------------------------------------------- #
IS_VERCEL = bool(os.environ.get("VERCEL"))

if not IS_VERCEL:
    # Lokal: baca file .env bila python-dotenv terpasang (variabel yang sudah diset tidak ditimpa)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _env_str(name, default="", strip=True):
    """Baca environment variable. Nilai kosong (mis. `MONGO_DB=` dari .env.example) dianggap belum diisi."""
    value = os.environ.get(name) or ""
    if not value.strip():
        return default
    return value.strip() if strip else value


PAY_INFO = _env_str("PAY_INFO")[:200]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

SECRET_KEY = _env_str("SECRET_KEY")
if not SECRET_KEY:
    if IS_VERCEL:
        raise RuntimeError("SECRET_KEY belum diset di Environment Variables Vercel.")
    SECRET_KEY = "dev-only-secret-ganti-di-produksi"

# Body JSON biasanya kecil. Hanya tambah/ubah produk yang boleh lebih besar karena membawa foto (data URL).
MAX_JSON_BYTES = 64 * 1024
MAX_PRODUCT_BODY_BYTES = 512 * 1024
PRODUCT_WRITE_RE = re.compile(r"/api/products(?:/[0-9a-fA-F]{24})?")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_VERCEL,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=MAX_PRODUCT_BODY_BYTES,   # batas 64 KB untuk route lain dijaga di guard()
)

# Role
ROLES = ("user", "admin", "master")
STAFF_ROLES = ("admin", "master")
ASSIGNABLE_ROLES = ("user", "admin")  # role yang boleh diberikan master

# Pesanan
ORDER_STATUS = ("pending", "paid", "shipped", "completed", "cancelled")
# Transisi yang boleh dilakukan staf (admin/master)
TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"shipped", "cancelled"},
    "shipped": {"completed"},
    "completed": set(),
    "cancelled": set(),
}
# Pelanggan hanya boleh membatalkan pesanan yang belum dibayar dan menerima pesanan yang dikirim
USER_TRANSITIONS = {("pending", "cancelled"), ("shipped", "completed")}
REVENUE_STATUS = ("paid", "shipped", "completed")
OPEN_STATUS = ("pending", "paid", "shipped")   # pesanan yang masih perlu ditangani staf
MAX_CART_LINES = 30
WIB_OFFSET = timedelta(hours=7)   # batas "hari ini" memakai waktu Indonesia Barat


def _env_int(name, default, minimum=1):
    try:
        return max(minimum, int(_env_str(name, str(default))))
    except ValueError:
        return default


# Pesanan yang belum dibayar dibatalkan otomatis dan stoknya dikembalikan
PENDING_TTL_HOURS = _env_int("PENDING_TTL_HOURS", 24)
LOG_RETENTION_DAYS = _env_int("LOG_RETENTION_DAYS", 90)   # log lebih lama dari ini dihapus otomatis oleh MongoDB
# Stok ditahan sejak pesanan dibuat, jadi satu akun tidak boleh menumpuk pesanan yang belum dibayar
MAX_PENDING_ORDERS = _env_int("MAX_PENDING_ORDERS", 3)
EXPIRE_SWEEP_SECONDS = 60   # jeda minimum antar penyapuan per instance
EXPIRE_BATCH = 50
MAX_QTY_PER_PRODUCT = 99

# Login dan password
MAX_FAILED_LOGIN = 5
LOCK_MINUTES = 10
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128

# Reset password lewat kode 6 angka yang dikirim ke email. Aktif hanya bila server SMTP dan pengirim diisi.
SMTP_HOST = _env_str("SMTP_HOST")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = _env_str("SMTP_USER")
SMTP_PASSWORD = _env_str("SMTP_PASSWORD", strip=False)
SMTP_FROM = _env_str("SMTP_FROM", SMTP_USER)
SMTP_TIMEOUT = 8            # detik; fungsi serverless tidak boleh menunggu server email terlalu lama
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_FROM)
RESET_CODE_LENGTH = 6
RESET_CODE_MINUTES = 15     # masa berlaku kode (dikirim ke frontend lewat respons /auth/forgot)
RESET_COOLDOWN_SECONDS = 60    # jeda minimum antar permintaan kode per akun (dipakai frontend untuk hitung mundur)
MAX_RESET_ATTEMPTS = 5      # tebakan kode yang boleh salah sebelum reset dikunci (terpisah dari kunci login)
RESET_LOCK_MINUTES = 10

# Batas jumlah data yang dikirim ke frontend
LOW_STOCK_LIMIT = 5        # stok <= angka ini dianggap menipis
LOW_STOCK_LIST_SIZE = 8
RECENT_ORDERS_SIZE = 5
PRODUCTS_LIMIT = 1000
ORDERS_LIMIT = 200         # pesanan selesai/batal yang ditampilkan (dan batas daftar pesanan pelanggan)
OPEN_ORDERS_LIMIT = 1000   # pengaman: pesanan berjalan hampir tidak pernah sebanyak ini
USERS_LIMIT = 500
LOGS_LIMIT = 150

# --------------------------------------------------------------------------- #
# Database (lazy + cache per instance serverless)
# --------------------------------------------------------------------------- #
_db = None

# Collection produk memakai nama dari daftar yang diwajibkan (master_product)
PRODUCT_COLLECTION = "master_product"
LEGACY_PRODUCT_COLLECTION = "products"


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def mongo_uri():
    uri = _env_str("MONGO_URI")
    if uri:
        return uri
    if IS_VERCEL:
        raise RuntimeError("MONGO_URI belum diset di Environment Variables Vercel.")
    return "mongodb://localhost:27017"


def mongo_db_name():
    return _env_str("MONGO_DB", "tokobiru")


def migrate_legacy_collections(db):
    """Pindahkan data dari collection lama `products` ke `master_product` (sekali saja)."""
    names = db.list_collection_names()
    if LEGACY_PRODUCT_COLLECTION in names and PRODUCT_COLLECTION not in names:
        db[LEGACY_PRODUCT_COLLECTION].rename(PRODUCT_COLLECTION)


def ensure_unique_order_code_index(db):
    """Kode pesanan dipakai sebagai referensi pembayaran, jadi harus unik.

    Bila data lama sudah memuat kode ganda, indeks tidak bisa dibuat. Aplikasi tetap berjalan
    (jangan sampai gagal start) dan masalahnya dicatat agar kode ganda itu dirapikan manual.
    """
    try:
        db.orders.create_index([("code", ASCENDING)], unique=True)
    except OperationFailure as exc:
        app.logger.error("Indeks unik orders.code gagal dibuat (ada kode ganda di data lama?): %s", exc)


def ensure_indexes(db):
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("email", ASCENDING)], unique=True)
    db[PRODUCT_COLLECTION].create_index([("name", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index([("category", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index([("stock", ASCENDING)])
    # Indeks teks untuk pencarian produk. Bobot: nama paling penting, lalu kategori, lalu deskripsi.
    # default_language="none": MongoDB tidak punya stemming/stop word bahasa Indonesia.
    # Satu collection hanya boleh punya satu indeks teks.
    db[PRODUCT_COLLECTION].create_index(
        [("name", "text"), ("category", "text"), ("description", "text")],
        weights={"name": 5, "category": 2, "description": 1},
        default_language="none",
        name="product_text",
    )
    db.orders.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.orders.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
    # daftar pesanan staf, "pesanan terbaru" di dashboard, dan ringkasan hari ini hanya memakai created_at
    db.orders.create_index([("created_at", DESCENDING)])
    db.orders.create_index([("paid_at", DESCENDING)])   # pendapatan hari ini
    # satu kunci idempotensi hanya boleh dipakai sekali per pelanggan (pesanan tanpa kunci tidak terkena)
    db.orders.create_index([("user_id", ASCENDING), ("idem_key", ASCENDING)], unique=True,
                           partialFilterExpression={"idem_key": {"$type": "string"}})
    ensure_unique_order_code_index(db)
    db.logs.create_index([("ts", DESCENDING)])
    # TTL: MongoDB menghapus log yang lebih tua dari LOG_RETENTION_DAYS, supaya koleksi tidak membengkak
    db.logs.create_index([("ts", ASCENDING)], expireAfterSeconds=LOG_RETENTION_DAYS * 86400, name="logs_ttl")


def get_db():
    global _db
    if _db is not None:
        return _db
    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=6000, appname="tokobiru")
    db = client[mongo_db_name()]
    migrate_legacy_collections(db)
    ensure_indexes(db)
    _db = db
    bootstrap(db)
    return db


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
class ApiError(Exception):
    def __init__(self, message, status=400, fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.fields = fields or {}


@app.errorhandler(ApiError)
def handle_api_error(e):
    payload = {"error": e.message}
    if e.fields:
        payload["fields"] = e.fields
    return jsonify(payload), e.status


@app.errorhandler(PyMongoError)
def handle_mongo_error(e):
    app.logger.error("MongoDB error: %s", e)
    return jsonify({"error": "Database tidak dapat diakses. Coba lagi sebentar."}), 503


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint tidak ditemukan"}), 404
    return Response("Halaman tidak ditemukan", status=404, mimetype="text/plain")


@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Metode tidak diizinkan"}), 405


@app.errorhandler(413)
def handle_413(e):
    return jsonify({"error": "Data terlalu besar"}), 413


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    """Penjaring terakhir: error HTTP lain diteruskan apa adanya, sisanya jadi 500."""
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    app.logger.exception("Unhandled error")
    return jsonify({"error": "Terjadi kesalahan pada server"}), 500


# --------------------------------------------------------------------------- #
# Sanitasi & validasi
# --------------------------------------------------------------------------- #
TAG_RE = re.compile(r"<[^>]*>")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
BLANK_LINES_RE = re.compile(r"\n{3,}")
USERNAME_RE = re.compile(r"[a-z0-9_]{3,20}")
EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}")
PERSON_RE = re.compile(r"[A-Za-zÀ-ÿ0-9 .,'\-]+")
OID_RE = re.compile(r"[0-9a-fA-F]{24}")
LETTER_RE = re.compile(r"[A-Za-z]")
DIGIT_RE = re.compile(r"\d")
INT_TEXT_RE = re.compile(r"-?\d{1,12}")
PHONE_RE = re.compile(r"\+?\d{8,15}")
PHONE_ERROR = "Isi nomor HP yang benar, contoh 081234567890"

NAME_ERROR = "Nama hanya boleh huruf, angka, spasi, titik, koma, apostrof, strip"
USERNAME_ERROR = "Username 3-20 karakter: huruf kecil, angka, underscore"
EMAIL_ERROR = "Format email tidak valid"
RESET_CODE_RE = re.compile(r"\d{6}")
RESET_CODE_ERROR = "Kode terdiri dari 6 angka"
RESET_FAILED_ERROR = "Kode salah atau sudah kedaluwarsa. Minta kode baru bila perlu."


def sanitize(value, multiline=False):
    """Bersihkan teks: normalisasi unicode, buang karakter kontrol & tag HTML."""
    value = unicodedata.normalize("NFKC", value)
    value = CTRL_RE.sub("", value)
    value = TAG_RE.sub("", value)
    value = value.replace("<", "").replace(">", "")
    if multiline:
        value = value.replace("\r", "")
        value = "\n".join(" ".join(line.split()) for line in value.split("\n"))
        value = BLANK_LINES_RE.sub("\n\n", value)
    else:
        value = " ".join(value.split())
    return value.strip()


def parse_int(raw):
    """Ubah bilangan bulat (angka atau teks angka) menjadi int; None bila tidak valid."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and INT_TEXT_RE.fullmatch(raw.strip()):
        return int(raw.strip())
    return None


def is_strong_password(password):
    return (
        len(password) >= PASSWORD_MIN_LEN
        and bool(LETTER_RE.search(password))
        and bool(DIGIT_RE.search(password))
    )


IMAGE_MAX_CHARS = 300_000   # panjang data URL (sekitar 220 KB); frontend mengecilkan foto menjadi sekitar 100 KB
IMAGE_RE = re.compile(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})")


def decode_image(raw):
    """Data URL gambar -> (bytes, mime). Isi diperiksa (base64 sah dan tanda file sesuai jenisnya),
    jadi hanya JPEG, PNG, dan WebP asli yang tersimpan. ValueError berisi pesan untuk pengguna."""
    if len(raw) > IMAGE_MAX_CHARS:
        raise ValueError("Foto terlalu besar. Pilih foto lain.")
    match = IMAGE_RE.fullmatch(raw)
    if not match:
        raise ValueError("Foto tidak valid. Gunakan JPG, PNG, atau WebP.")
    mime, payload = match.groups()
    try:
        data = base64.b64decode(payload, validate=True)
    except ValueError:
        raise ValueError("Foto tidak valid. Gunakan JPG, PNG, atau WebP.") from None
    signature_ok = (
        (mime == "image/jpeg" and data[:3] == b"\xff\xd8\xff")
        or (mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n")
        or (mime == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )
    if not signature_ok:
        raise ValueError("Foto tidak valid. Gunakan JPG, PNG, atau WebP.")
    return data, mime


class Form:
    """Validator sederhana: kumpulkan semua error per-field lalu raise sekali."""

    def __init__(self, data):
        self.data = data if isinstance(data, dict) else {}
        self.errors = {}
        self.out = {}

    def _empty(self, name, label, required):
        if required:
            self.errors[name] = f"{label} wajib diisi"
        else:
            self.out[name] = ""

    def text(self, name, label, min_len=0, max_len=100, required=True,
             multiline=False, regex=None, regex_msg=None, lower=False):
        raw = self.data.get(name)
        if raw is None or raw == "":
            return self._empty(name, label, required)
        if not isinstance(raw, str):  # cegah NoSQL injection ({"$ne": ...})
            self.errors[name] = f"{label} tidak valid"
            return
        value = sanitize(raw, multiline)
        if lower:
            value = value.lower()
        if not value:
            return self._empty(name, label, required)
        if len(value) < min_len:
            self.errors[name] = f"{label} minimal {min_len} karakter"
        elif len(value) > max_len:
            self.errors[name] = f"{label} maksimal {max_len} karakter"
        elif regex and not regex.fullmatch(value):
            self.errors[name] = regex_msg or f"Format {label} tidak valid"
        else:
            self.out[name] = value

    def password(self, name="password", label="Password", enforce_policy=True):
        raw = self.data.get(name)
        if not isinstance(raw, str) or raw == "":
            self.errors[name] = f"{label} wajib diisi"
            return
        if len(raw) > PASSWORD_MAX_LEN:
            self.errors[name] = f"{label} maksimal {PASSWORD_MAX_LEN} karakter"
        elif enforce_policy and not is_strong_password(raw):
            self.errors[name] = (
                f"{label} minimal {PASSWORD_MIN_LEN} karakter dan mengandung huruf serta angka"
            )
        else:
            self.out[name] = raw

    def integer(self, name, label, lo, hi):
        raw = self.data.get(name)
        if raw is None or raw == "" or isinstance(raw, bool):
            self.errors[name] = f"{label} wajib diisi"
            return
        number = parse_int(raw)
        if number is None:
            self.errors[name] = f"{label} harus berupa bilangan bulat"
        elif number < lo or number > hi:
            self.errors[name] = f"{label} harus antara {lo:,} dan {hi:,}".replace(",", ".")
        else:
            self.out[name] = number

    def image(self, name="image", label="Foto"):
        """Foto sebagai data URL. Kunci tidak dikirim: foto lama dibiarkan. Kosong: foto dihapus (None).
        Valid: (bytes, mime)."""
        if name not in self.data:
            return
        raw = self.data[name]
        if raw is None or raw == "":
            self.out[name] = None
            return
        if not isinstance(raw, str):
            self.errors[name] = f"{label} tidak valid"
            return
        try:
            self.out[name] = decode_image(raw)
        except ValueError as exc:
            self.errors[name] = str(exc)

    def choice(self, name, label, options):
        raw = self.data.get(name)
        if not isinstance(raw, str) or raw not in options:
            self.errors[name] = f"{label} tidak valid"
        else:
            self.out[name] = raw

    def done(self):
        if self.errors:
            raise ApiError("Periksa kembali isian Anda", 422, self.errors)
        return self.out


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Body JSON tidak valid", 400)
    return data


def object_id(value, label="ID"):
    if not isinstance(value, str) or not OID_RE.fullmatch(value):
        raise ApiError(f"{label} tidak valid", 400)
    return ObjectId(value)


# --------------------------------------------------------------------------- #
# Serialisasi (dokumen Mongo -> JSON)
# --------------------------------------------------------------------------- #
HIDDEN_FIELDS = ("password_hash", "failed", "locked_until", "idem_key", "session_version",
                 "reset_code_hash", "reset_expires", "reset_sent_at", "reset_failed", "reset_locked_until",
                 "image", "image_type", "image_v")   # foto produk: dikirim lewat /api/products/<id>/image


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
    """Dokumen Mongo -> dict siap JSON (tanpa field rahasia, `_id` menjadi `id`)."""
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


def public_user(user):
    if not user:
        return None
    return {"id": str(user["_id"]), "username": user["username"], "name": user["name"],
            "email": user["email"], "role": user["role"]}


# --------------------------------------------------------------------------- #
# Akun: form dan dokumen pengguna
# --------------------------------------------------------------------------- #
def user_form(data, with_role=False):
    """Validasi data akun (dipakai pendaftaran, tambah pengguna, dan CLI master)."""
    form = Form(data)
    form.text("name", "Nama lengkap", 2, 50, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.text("username", "Username", 3, 20, lower=True, regex=USERNAME_RE,
              regex_msg=USERNAME_ERROR)
    form.text("email", "Email", 5, 120, lower=True, regex=EMAIL_RE, regex_msg=EMAIL_ERROR)
    form.password()
    if with_role:
        form.choice("role", "Role", ASSIGNABLE_ROLES)
    return form.done()


def new_user_doc(fields, role):
    """Dokumen user baru. `fields` berisi name, username, email, password."""
    return {
        "name": fields["name"],
        "username": fields["username"],
        "email": fields["email"],
        "password_hash": generate_password_hash(fields["password"]),
        "role": role,
        "active": True,
        "created_at": utcnow(),
        "failed": 0,
    }


# --------------------------------------------------------------------------- #
# Auth: session, RBAC, CSRF, audit
# --------------------------------------------------------------------------- #
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def client_ip():
    if not has_request_context():   # mis. penyapuan dari skrip, bukan dari request
        return ""
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.remote_addr or "")
    return sanitize(ip)[:45]


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid and OID_RE.fullmatch(str(uid)):
        user = get_db().users.find_one({"_id": ObjectId(uid)})
        # session_version naik tiap ganti password: sesi lama (versi berbeda) tidak berlaku lagi
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
    """Catat aktivitas. Kegagalan mencatat log tidak boleh menggagalkan request."""
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


@app.before_request
def guard():
    if request.path.startswith("/api/") and request.method not in SAFE_METHODS:
        too_big = request.content_length and request.content_length > MAX_JSON_BYTES
        if too_big and not (request.method in ("POST", "PUT") and PRODUCT_WRITE_RE.fullmatch(request.path)):
            raise ApiError("Data terlalu besar", 413)
        if not csrf_token_valid():
            raise ApiError("Token keamanan tidak valid. Muat ulang halaman.", 403)
        if not request.is_json:
            raise ApiError("Content-Type harus application/json", 415)


@app.after_request
def secure_headers(resp):
    resp.headers.update(SECURITY_HEADERS)
    if request.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")   # route foto mengatur cache-nya sendiri
    elif resp.mimetype == "text/html":
        resp.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        resp.headers["Cache-Control"] = "no-cache"
    elif request.path.startswith("/static/"):
        # Modul JS saling mengimpor, jadi browser wajib memeriksa versi terbaru (ETag) sebelum memakai
        # cache. Bila file tidak berubah server cukup membalas 304; setelah deploy tidak ada campuran
        # file lama dan baru.
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# --------------------------------------------------------------------------- #
# Routes: Auth
# --------------------------------------------------------------------------- #
DUMMY_HASH = generate_password_hash(secrets.token_hex(8))


def start_session(user):
    session.clear()
    session.permanent = True
    session["uid"] = str(user["_id"])
    session["sv"] = user.get("session_version", 0)
    session["csrf"] = secrets.token_urlsafe(32)


def record_failed_login(db, user, now):
    """Tambah hitungan gagal login; kunci akun sementara bila sudah mencapai batas."""
    failed = user.get("failed", 0) + 1
    changes = {"failed": failed}
    if failed >= MAX_FAILED_LOGIN:
        changes = {"failed": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}
    db.users.update_one({"_id": user["_id"]}, {"$set": changes})


def account_locked_error():
    return ApiError(
        f"Akun dikunci sementara karena terlalu banyak percobaan. Coba lagi dalam {LOCK_MINUTES} menit.", 429)


@app.get("/api/auth/me")
def auth_me():
    user = current_user()   # bisa membersihkan sesi (akun nonaktif / sesi dicabut), jadi dipanggil sebelum membuat csrf
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"user": public_user(user), "csrf": session["csrf"], "pay_info": PAY_INFO,
                    "reset_enabled": EMAIL_ENABLED})


@app.post("/api/auth/register")
def auth_register():
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


@app.post("/api/auth/login")
def auth_login():
    form = Form(json_body())
    form.text("identifier", "Username/email", 1, 120, lower=True)
    form.password("password", "Password", enforce_policy=False)
    clean = form.done()
    identifier = clean["identifier"]
    db = get_db()
    user = db.users.find_one({"$or": [{"username": identifier}, {"email": identifier}]})
    now = utcnow()
    if user and user.get("locked_until") and user["locked_until"] > now:
        raise account_locked_error()
    # Hash palsu tetap diperiksa agar waktu respons sama untuk akun yang tidak ada
    stored_hash = user["password_hash"] if user else DUMMY_HASH
    password_ok = check_password_hash(stored_hash, clean["password"])
    if user is None or not password_ok:
        if user:
            record_failed_login(db, user, now)
        # Teks di kolom username sering berisi password yang salah ketik, jadi hanya dicatat bila akunnya memang ada
        audit("login_gagal", f"identifier={identifier[:40]}" if user else "akun tidak dikenal")
        raise ApiError("Username/email atau password salah", 401)
    if not user.get("active", True):
        raise ApiError("Akun Anda dinonaktifkan. Silakan hubungi pengelola toko.", 403)
    db.users.update_one({"_id": user["_id"]},
                        {"$set": {"failed": 0, "last_login": now, "locked_until": None}})
    start_session(user)
    audit("login", "berhasil masuk", user)
    return jsonify({"user": public_user(user), "csrf": session["csrf"]})


@app.post("/api/auth/logout")
def auth_logout():
    if session.get("uid"):
        audit("logout", "")
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"ok": True, "csrf": session["csrf"]})


@app.patch("/api/auth/password")
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
        raise account_locked_error()
    # Password lama yang salah dihitung ke batas gagal login yang sama, supaya sesi yang dicuri tidak
    # bisa dipakai menebak password lewat endpoint ini.
    if not check_password_hash(user["password_hash"], clean["current_password"]):
        record_failed_login(db, user, now)
        audit("password_gagal", "password lama salah")
        raise ApiError("Password lama salah", 422, {"current_password": "Password lama salah"})
    if clean["new_password"] == clean["current_password"]:
        message = "Password baru harus berbeda dari yang lama"
        raise ApiError(message, 422, {"new_password": message})
    db.users.update_one({"_id": user["_id"]}, {
        "$set": {"password_hash": generate_password_hash(clean["new_password"]),
                 "failed": 0, "locked_until": None},
        "$inc": {"session_version": 1}})
    # sesi yang dipakai sekarang ikut naik versi; sesi di perangkat lain tidak berlaku lagi
    session["sv"] = db.users.find_one({"_id": user["_id"]}).get("session_version", 1)
    audit("password_ubah", "")
    return jsonify({"ok": True})


# --- Lupa password: kode 6 angka lewat email -------------------------------------------------- #
RESET_FIELDS = {"reset_code_hash": "", "reset_expires": "", "reset_sent_at": ""}   # untuk $unset
# Penghitung tebakan sengaja TIDAK ikut RESET_FIELDS: gagal kirim email tidak boleh menghapus kunci.
# Hanya dibersihkan saat reset berhasil.
RESET_GUARD_FIELDS = {"reset_failed": "", "reset_locked_until": ""}


def send_email(to, subject, body, html=None, inline_images=None):
    """Kirim email lewat SMTP: teks biasa, plus versi HTML bila `html` diberikan. Dipisah dari route supaya mudah diganti di tes.
    `inline_images`: {cid: bytes PNG} untuk gambar yang dipanggil di HTML lewat src="cid:..." (ikut terkirim di dalam email)."""
    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
        for cid, data in (inline_images or {}).items():
            message.get_payload()[1].add_related(data, "image", "png", cid=f"<{cid}>", disposition="inline")
    use_ssl = SMTP_PORT == 465
    # Konteks bawaan smtplib TIDAK memeriksa sertifikat server; create_default_context() memeriksanya
    context = ssl.create_default_context()
    if use_ssl:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT)
    with server:
        if not use_ssl:
            server.starttls(context=context)
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


def reset_email_text(name, code):
    return (f"Halo {name},\n\n"
            f"Kode reset password TokoBiru Anda: {code}\n\n"
            f"Kode berlaku {RESET_CODE_MINUTES} menit dan hanya bisa dipakai sekali.\n"
            "Jangan bagikan kode ini kepada siapa pun, termasuk yang mengaku dari TokoBiru.\n"
            "Jika Anda tidak merasa memintanya, abaikan email ini; password Anda tidak berubah.\n")


EMAIL_LOGO_FILE = os.path.join(BASE_DIR, "static", "icons", "icon-192.png")


def load_email_logo():
    """Logo TokoBiru (PNG) untuk header email, atau None bila file tidak terbaca: email tetap terkirim, hanya tanpa logo."""
    try:
        with open(EMAIL_LOGO_FILE, "rb") as f:
            return f.read()
    except OSError:
        return None


def reset_email_html(name, code, logo_cid=None):
    """Versi HTML email kode reset. Hanya `name` yang berasal dari data pengguna, dan di-escape.
    `logo_cid`: bila diisi, logo ditampilkan dari gambar inline dengan CID itu (lihat send_email)."""
    name = html_escape(name)
    mark = (f'<td style="padding-right:10px"><img src="cid:{logo_cid}" width="40" height="40" alt="" '
            'style="display:block;border:0;border-radius:11px"></td>') if logo_cid else ""
    brand = ('<table role="presentation" cellpadding="0" cellspacing="0"><tr>' + mark +
             '<td style="font-size:22px;font-weight:bold;color:#0c2342;letter-spacing:-0.5px">TokoBiru</td></tr></table>')
    return f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:24px 12px;background:#eef4fb;font-family:Arial,Helvetica,sans-serif;color:#0c2342">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden">
<tr><td style="border-top:4px solid #0b5fc4;padding:20px 28px 0">{brand}</td></tr>
<tr><td style="padding:28px">
<p style="margin:0 0 12px;font-size:16px;line-height:1.5">Halo {name},</p>
<p style="margin:0 0 16px;font-size:16px;line-height:1.5">Gunakan kode ini untuk membuat password baru:</p>
<p style="margin:0 0 8px;padding:16px;background:#e3eefc;border-radius:10px;text-align:center;font-size:32px;font-weight:bold;font-family:Consolas,Menlo,monospace;color:#0a4ea3"><span style="letter-spacing:6px;-webkit-user-select:all;user-select:all">{code}</span></p>
<p style="margin:0 0 20px;font-size:13px;line-height:1.5;color:#566f89;text-align:center">Ketuk dan tahan kode di atas, lalu pilih Salin. Atau salin dari sini: <span style="font-family:Consolas,Menlo,monospace;font-size:15px;color:#0c2342;-webkit-user-select:all;user-select:all">{code}</span></p>
<p style="margin:0 0 12px;font-size:14px;line-height:1.6">Kode berlaku {RESET_CODE_MINUTES} menit dan hanya bisa dipakai sekali. Jangan bagikan kode ini kepada siapa pun, termasuk yang mengaku dari TokoBiru.</p>
<p style="margin:0;font-size:14px;line-height:1.6;color:#566f89">Jika Anda tidak merasa memintanya, abaikan email ini; password Anda tidak berubah.</p>
</td></tr></table>
</td></tr></table>
</body></html>"""


def new_reset_code():
    return f"{secrets.randbelow(10 ** RESET_CODE_LENGTH):0{RESET_CODE_LENGTH}d}"


def reset_code_digest(user_id, code):
    """Kode disimpan sebagai HMAC (terikat ke akun), bukan teks asli."""
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


@app.post("/api/auth/forgot")
def auth_forgot():
    """Kirim kode reset ke email akun. Jawabannya selalu sama, terdaftar atau tidak, agar daftar akun tidak bisa ditebak."""
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
        except Exception as exc:   # smtplib punya banyak jenis error; apa pun yang terjadi, kode tidak jadi dipakai
            app.logger.error("Gagal mengirim email reset password: %s", exc)
            db.users.update_one({"_id": user["_id"]}, {"$unset": RESET_FIELDS})   # boleh langsung coba lagi
        else:
            audit("reset_minta", "kode dikirim ke email", user)
    # Angka konstan, sama untuk email terdaftar maupun tidak: frontend memakainya untuk hitung mundur dan teks bantuan
    return jsonify({"ok": True, "retry_after": RESET_COOLDOWN_SECONDS, "expires_minutes": RESET_CODE_MINUTES})


@app.post("/api/auth/reset")
def auth_reset():
    """Ganti password memakai kode dari email. Kode sekali pakai.

    Tebakan kode punya penghitung sendiri (reset_failed / reset_locked_until), terpisah dari kunci login:
    akun yang terkunci karena salah login tetap bisa direset dengan kode benar, dan tebakan kode salah
    tidak ikut mengunci login pemilik akun."""
    require_email_enabled()
    form = Form(json_body())
    form.text("email", "Email", 5, 120, lower=True, regex=EMAIL_RE, regex_msg=EMAIL_ERROR)
    form.text("code", "Kode", RESET_CODE_LENGTH, RESET_CODE_LENGTH, regex=RESET_CODE_RE, regex_msg=RESET_CODE_ERROR)
    form.password("new_password", "Password baru")
    clean = form.done()   # kode tidak disentuh bila isian tidak valid, jadi bisa dipakai lagi setelah diperbaiki
    db = get_db()
    user = db.users.find_one({"email": clean["email"]})
    now = utcnow()
    # Hanya akun dengan kode yang sedang berlaku yang punya sesuatu untuk ditebak
    pending = bool(user and user.get("active", True) and user.get("reset_code_hash")
                   and user.get("reset_expires") and user["reset_expires"] > now)
    if pending:
        # Jatah tebakan diambil secara atomik SEBELUM kode dicocokkan. Request yang datang bersamaan
        # tidak bisa sama-sama membaca hitungan lama lalu menebak tanpa terhitung.
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
            # Tebakan beruntun yang lolos sebelum kunci terpasang tidak dicocokkan. Kunci dipasang lagi di sini
            # (idempoten) supaya penghitung tidak pernah menggantung di atas batas tanpa kunci.
            lock_reset(db, user, now)
            raise reset_locked_error()
        # Kode dicocokkan di filter update (bukan di Python), jadi dua request bersamaan tidak bisa memakai kode yang sama
        result = db.users.update_one(
            {"_id": user["_id"], "reset_code_hash": reset_code_digest(user["_id"], clean["code"])},
            {"$set": {"password_hash": generate_password_hash(clean["new_password"]),
                      "failed": 0, "locked_until": None},
             "$inc": {"session_version": 1},   # semua sesi lama, di perangkat mana pun, tidak berlaku lagi
             "$unset": {**RESET_FIELDS, **RESET_GUARD_FIELDS}})
        if result.modified_count == 1:
            audit("password_reset", "lewat kode email", user)
            return jsonify({"ok": True})
        if tries >= MAX_RESET_ATTEMPTS:
            lock_reset(db, user, now)
            audit("reset_gagal", "kode salah, reset dikunci sementara", user)
            raise reset_locked_error()
        audit("reset_gagal", "kode salah", user)
    # Pesan sama untuk email tak dikenal, tanpa kode aktif, kode salah, dan kode kedaluwarsa
    raise ApiError(RESET_FAILED_ERROR, 422, {"code": "Kode salah atau sudah kedaluwarsa"})


@app.post("/api/auth/reset/check")
def auth_reset_check():
    """Periksa kode reset TANPA memakainya, supaya layar kode bisa menolak kode salah sebelum meminta password baru.

    Memakai penghitung tebakan yang sama dengan /auth/reset: tebakan salah di sini dan di sana dijumlahkan,
    jadi endpoint ini bukan jalan memutar untuk menebak lebih dari batas. Tebakan yang benar dikembalikan
    jatahnya dan kodenya tetap berlaku; yang memakainya hanya /auth/reset. Jawaban untuk email tak dikenal,
    tanpa kode aktif, kode salah, dan kedaluwarsa sama persis."""
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
            # kode benar: kembalikan jatah tebakan yang barusan diambil; kode tetap berlaku sampai /auth/reset
            db.users.update_one({"_id": user["_id"], "reset_failed": {"$gt": 0}}, {"$inc": {"reset_failed": -1}})
            return jsonify({"ok": True})
        if tries >= MAX_RESET_ATTEMPTS:
            lock_reset(db, user, now)
            audit("reset_gagal", "kode salah, reset dikunci sementara", user)
            raise reset_locked_error()
        audit("reset_gagal", "kode salah", user)
    raise ApiError(RESET_FAILED_ERROR, 422, {"code": "Kode salah atau sudah kedaluwarsa"})


# --------------------------------------------------------------------------- #
# Routes: Produk
# --------------------------------------------------------------------------- #
def product_form(data):
    form = Form(data)
    form.text("name", "Nama produk", 2, 80)
    form.text("category", "Kategori", 2, 30)
    form.integer("price", "Harga", 100, 100_000_000)
    form.integer("stock", "Stok", 0, 100_000)
    form.text("description", "Deskripsi", 0, 300, required=False, multiline=True)
    form.image("image", "Foto produk")
    return form.done()


# Bytes foto tidak ikut dibaca saat daftar produk dimuat; klien mengambilnya lewat /api/products/<id>/image
NO_IMAGE = {"image": 0}


def product_json(doc):
    """Produk -> JSON. Bila ada foto, `photo` berisi alamat fotonya (?v= berganti saat foto diganti,
    jadi browser boleh menyimpannya lama)."""
    out = serialize(doc)
    if doc.get("image_v"):
        out["photo"] = f"/api/products/{out['id']}/image?v={int(doc['image_v'])}"
    return out


def split_image(clean):
    """Pisahkan foto dari isian produk. Mengembalikan (field untuk $set, field untuk $unset)."""
    if "image" not in clean:
        return {}, {}
    image = clean.pop("image")
    if image is None:
        return {}, {"image": "", "image_type": "", "image_v": ""}
    data, mime = image
    return {"image": data, "image_type": mime, "image_v": int(time.time() * 1000)}, {}


def text_search_term(search):
    """Siapkan teks untuk $text. Tanda kutip dan awalan '-' punya arti khusus di $text
    (frasa dan pengecualian), jadi dibuang supaya masukan pengguna dibaca sebagai kata biasa."""
    words = (word.replace('"', "").replace("\\", "").lstrip("-") for word in search.split())
    return " ".join(word for word in words if word)


def search_products(db, search, category):
    """Cari produk. Tahap 1: indeks teks, diurutkan menurut relevansi. Tahap 2 (bila tahap 1 kosong,
    mis. kata belum lengkap seperti "ber" untuk "Beras", atau indeks teks tidak tersedia): regex pada nama.

    Mengembalikan (daftar produk, filter yang dipakai) supaya total dihitung dengan filter yang sama."""
    collection = db[PRODUCT_COLLECTION]
    base = {"category": category} if category else {}
    term = text_search_term(search)
    if term:
        text_query = {**base, "$text": {"$search": term}}
        try:
            docs = list(collection.find(text_query, {"_score": {"$meta": "textScore"}, **NO_IMAGE})
                        .sort([("_score", {"$meta": "textScore"})]).limit(PRODUCTS_LIMIT))
        except OperationFailure as exc:   # mis. indeks teks gagal dibuat; pencarian tetap jalan lewat regex
            app.logger.warning("Pencarian teks gagal, memakai regex: %s", exc)
            docs = []
        if docs:
            for doc in docs:
                doc.pop("_score", None)   # skor hanya untuk pengurutan, tidak dikirim ke klien
            return docs, text_query
    regex_query = {**base, "name": {"$regex": re.escape(search), "$options": "i"}}
    docs = list(collection.find(regex_query, NO_IMAGE).sort("name", 1).limit(PRODUCTS_LIMIT))
    return docs, regex_query


@app.get("/api/products")
@login_required
def products_list():
    db = get_db()
    sweep_expired_orders(db)   # stok dari pesanan kedaluwarsa kembali sebelum katalog dikirim
    search = sanitize(str(request.args.get("q", ""))[:50])
    category = sanitize(str(request.args.get("category", ""))[:30])
    if search:
        docs, query = search_products(db, search, category)
    else:
        query = {"category": category} if category else {}
        docs = list(db[PRODUCT_COLLECTION].find(query, NO_IMAGE).sort("name", 1).limit(PRODUCTS_LIMIT))
    categories = sorted(c for c in db[PRODUCT_COLLECTION].distinct("category") if isinstance(c, str))
    return jsonify({"products": [product_json(p) for p in docs], "categories": categories,
                    "total": db[PRODUCT_COLLECTION].count_documents(query)})


@app.post("/api/products")
@roles_required(*STAFF_ROLES)
def products_create():
    clean = product_form(json_body())
    image_set, _ = split_image(clean)
    clean.update(image_set)
    clean["created_at"] = clean["updated_at"] = utcnow()
    db = get_db()
    result = db[PRODUCT_COLLECTION].insert_one(clean)
    audit("produk_tambah", clean["name"] + (" (dengan foto)" if image_set else ""))
    created = db[PRODUCT_COLLECTION].find_one({"_id": result.inserted_id}, NO_IMAGE)
    return jsonify({"product": product_json(created)}), 201


def parse_base_stock(data):
    """Stok yang dilihat staf saat membuka form ubah; None bila klien tidak mengirimnya."""
    raw = data.get("base_stock")
    if raw is None or raw == "":
        return None
    value = parse_int(raw) if not isinstance(raw, bool) else None
    if value is None or not 0 <= value <= 100_000:
        raise ApiError("Periksa kembali isian Anda", 422, {"stock": "Stok awal tidak valid. Muat ulang halaman."})
    return value


@app.put("/api/products/<product_id>")
@roles_required(*STAFF_ROLES)
def products_update(product_id):
    target_id = object_id(product_id, "Produk")
    body = json_body()
    clean = product_form(body)
    image_set, image_unset = split_image(clean)
    clean.update(image_set)
    base_stock = parse_base_stock(body)
    clean["updated_at"] = utcnow()
    db = get_db()
    collection = db[PRODUCT_COLLECTION]

    # Bila base_stock dikirim, stok diubah sebagai selisih ($inc) dari yang dilihat staf, sehingga
    # penjualan yang terjadi saat form terbuka tidak tertimpa. Tanpa base_stock: ditimpa (perilaku lama).
    query = {"_id": target_id}
    new_stock = clean.pop("stock")
    update = {"$set": clean}
    if image_unset:
        update["$unset"] = image_unset
    delta = None
    if base_stock is None:
        clean["stock"] = new_stock
    else:
        delta = new_stock - base_stock
        if delta:
            update["$inc"] = {"stock": delta}
        if delta < 0:
            query["stock"] = {"$gte": -delta}   # jangan sampai stok jadi negatif

    result = collection.update_one(query, update)
    if result.matched_count == 0:
        if not collection.find_one({"_id": target_id}):
            raise ApiError("Produk tidak ditemukan", 404)
        raise ApiError("Stok berubah karena ada penjualan. Muat ulang halaman lalu coba lagi.", 409)
    photo_note = " (foto diganti)" if image_set else " (foto dihapus)" if image_unset else ""
    audit("produk_ubah", clean["name"] + (f" (stok {delta:+d})" if delta else "") + photo_note)
    return jsonify({"product": product_json(collection.find_one({"_id": target_id}, NO_IMAGE))})


@app.get("/api/products/<product_id>/image")
@login_required
def products_image(product_id):
    target_id = object_id(product_id, "Produk")
    doc = get_db()[PRODUCT_COLLECTION].find_one({"_id": target_id}, {"image": 1, "image_type": 1})
    if not doc or not doc.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(doc["image"]), mimetype=doc.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"   # alamat berganti (?v=) saat foto berganti
    return resp


@app.delete("/api/products/<product_id>")
@roles_required(*STAFF_ROLES)
def products_delete(product_id):
    target_id = object_id(product_id, "Produk")
    product = get_db()[PRODUCT_COLLECTION].find_one_and_delete({"_id": target_id})
    if not product:
        raise ApiError("Produk tidak ditemukan", 404)
    audit("produk_hapus", product["name"])
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# Routes: Pesanan
# --------------------------------------------------------------------------- #
ORDER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # tanpa 0/O dan 1/I/L yang mudah tertukar saat diketik
ORDER_CODE_LENGTH = 6          # 31^6 = hampir 900 juta kemungkinan per hari
ORDER_CODE_ATTEMPTS = 5
IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{8,64}")


def new_order_code():
    suffix = "".join(secrets.choice(ORDER_CODE_ALPHABET) for _ in range(ORDER_CODE_LENGTH))
    return "TB-" + utcnow().strftime("%y%m%d") + "-" + suffix


def parse_cart_items(items):
    """Validasi isi keranjang dan gabungkan produk yang sama -> {ObjectId: jumlah}."""
    if not isinstance(items, list) or not items or len(items) > MAX_CART_LINES:
        raise ApiError("Keranjang kosong atau terlalu banyak item", 422)
    wanted = {}
    for item in items:
        if not isinstance(item, dict):
            raise ApiError("Item keranjang tidak valid", 422)
        product_id = object_id(item.get("product_id"), "Produk")
        form = Form(item)
        form.integer("qty", "Jumlah", 1, MAX_QTY_PER_PRODUCT)
        wanted[product_id] = wanted.get(product_id, 0) + form.done()["qty"]
    if any(qty > MAX_QTY_PER_PRODUCT for qty in wanted.values()):
        raise ApiError(f"Maksimal {MAX_QTY_PER_PRODUCT} unit per produk", 422)
    return wanted


def parse_expected_prices(items):
    """Harga per produk yang dilihat pelanggan saat checkout -> {ObjectId: harga}.

    Opsional: baris tanpa `price` (klien lama) tidak diperiksa. Dipanggil setelah parse_cart_items,
    jadi `items` dan `product_id` di dalamnya sudah tervalidasi.
    """
    expected = {}
    for item in items:
        if item.get("price") is None:
            continue
        form = Form(item)
        form.integer("price", "Harga", 1, 100_000_000)
        expected[ObjectId(item["product_id"])] = form.done()["price"]
    return expected


def format_rupiah(amount):
    return "Rp" + f"{amount:,}".replace(",", ".")


def release_stock(db, reserved):
    """Kembalikan stok. `reserved` berisi pasangan (product_id, jumlah)."""
    for product_id, qty in reserved:
        db[PRODUCT_COLLECTION].update_one({"_id": product_id}, {"$inc": {"stock": qty}})


_last_sweep = None


def sweep_expired_orders(db, force=False):
    """Batalkan pesanan 'pending' yang melewati batas bayar dan kembalikan stoknya.

    Dijalankan malas (saat ada request) dan dibatasi sekali per EXPIRE_SWEEP_SECONDS per instance,
    karena di serverless tidak ada proses latar belakang. Kegagalan di sini tidak boleh
    menggagalkan request utama.
    """
    global _last_sweep
    now_ts = time.monotonic()
    if not force and _last_sweep is not None and now_ts - _last_sweep < EXPIRE_SWEEP_SECONDS:
        return 0
    _last_sweep = now_ts

    cancelled = 0
    try:
        cutoff = utcnow() - timedelta(hours=PENDING_TTL_HOURS)
        stale = list(db.orders.find({"status": "pending", "created_at": {"$lt": cutoff}}).limit(EXPIRE_BATCH))
        for order in stale:
            # status dicek ulang pada filter: pesanan yang baru dibayar tidak ikut dibatalkan
            result = db.orders.update_one(
                {"_id": order["_id"], "status": "pending"},
                {"$set": {"status": "cancelled", "cancel_reason": "expired", "updated_at": utcnow()}})
            if result.modified_count != 1:
                continue
            release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
            audit("pesanan_kedaluwarsa", order["code"], {"username": "sistem", "role": "-"})
            cancelled += 1
    except PyMongoError as exc:
        app.logger.error("Penyapuan pesanan kedaluwarsa gagal: %s", exc)
    return cancelled


def cancel_pending_orders(db, user_id, reason):
    """Batalkan semua pesanan 'pending' milik satu akun dan kembalikan stoknya segera.

    Dipakai saat akun dinonaktifkan atau dihapus, supaya stok tidak tertahan sampai pesanan kedaluwarsa.
    Status dicek ulang pada filter, jadi pesanan yang baru dibayar tidak ikut dibatalkan.
    """
    cancelled = 0
    for order in db.orders.find({"user_id": user_id, "status": "pending"}):
        result = db.orders.update_one(
            {"_id": order["_id"], "status": "pending"},
            {"$set": {"status": "cancelled", "cancel_reason": reason, "updated_at": utcnow()}})
        if result.modified_count != 1:
            continue
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
        cancelled += 1
    return cancelled


def reserve_stock(db, wanted, expected_prices=None):
    """Kurangi stok tiap produk secara atomik dan kembalikan (reserved, baris pesanan).

    Bila satu produk gagal, stok produk lain yang sudah dikurangi dikembalikan. Bila `expected_prices`
    diberikan, pesanan ditolak (409) untuk produk yang harganya sudah berbeda dari yang dilihat pelanggan;
    harga yang tercatat di pesanan selalu harga yang sama dengan yang diperiksa di sini.
    """
    reserved, lines = [], []
    try:
        for product_id, qty in wanted.items():
            product = db[PRODUCT_COLLECTION].find_one({"_id": product_id}, NO_IMAGE)
            if not product:
                raise ApiError("Ada produk yang sudah tidak tersedia", 404)
            seen_price = (expected_prices or {}).get(product_id)
            if seen_price is not None and seen_price != product["price"]:
                raise ApiError(
                    f"Harga '{product['name']}' berubah dari {format_rupiah(seen_price)} menjadi "
                    f"{format_rupiah(product['price'])}. Keranjang sudah diperbarui, periksa lagi sebelum memesan.",
                    409)
            # Pengurangan stok atomik: hanya berhasil jika stok cukup
            result = db[PRODUCT_COLLECTION].update_one(
                {"_id": product_id, "stock": {"$gte": qty}}, {"$inc": {"stock": -qty}})
            if result.modified_count != 1:
                raise ApiError(f"Stok '{product['name']}' tidak mencukupi (tersisa {product['stock']})", 409)
            reserved.append((product_id, qty))
            lines.append({"product_id": product_id, "name": product["name"],
                          "price": product["price"], "qty": qty,
                          "subtotal": product["price"] * qty})
    except Exception:
        release_stock(db, reserved)
        raise
    return reserved, lines


class OrderReplay(Exception):
    """Kunci idempotensi sudah dipakai: pesanan yang sama sudah tersimpan."""

    def __init__(self, order):
        super().__init__("order replay")
        self.order = order


def idempotency_key():
    """Header Idempotency-Key (opsional). Klien mengirim kunci yang sama saat mengulang request yang
    sama, sehingga jaringan yang putus tidak menghasilkan pesanan ganda."""
    raw = request.headers.get("Idempotency-Key", "").strip()
    if not raw:
        return None
    if not IDEMPOTENCY_KEY_RE.fullmatch(raw):
        raise ApiError("Idempotency-Key tidak valid", 422)
    return raw


def replayed_order(db, user, key, wanted):
    """Pesanan yang sudah dibuat dengan kunci ini (None bila belum ada).

    Kunci yang sama untuk isi keranjang berbeda ditolak, bukan diam-diam mengembalikan pesanan lain.
    """
    if key is None:
        return None
    order = db.orders.find_one({"user_id": user["_id"], "idem_key": key})
    if order is None:
        return None
    if {item["product_id"]: item["qty"] for item in order["items"]} != wanted:
        raise ApiError("Kunci permintaan ini sudah dipakai untuk pesanan yang berbeda", 422)
    return order


def insert_order(db, order, user, key):
    """Simpan pesanan dengan kode unik; kode diundi ulang bila bentrok.

    Bila bentrokan ternyata karena kunci idempotensi (dua request yang sama berjalan bersamaan),
    lempar OrderReplay berisi pesanan yang sudah tersimpan.
    """
    for _ in range(ORDER_CODE_ATTEMPTS):
        order["code"] = new_order_code()
        try:
            db.orders.insert_one(order)
            return order
        except DuplicateKeyError:
            order.pop("_id", None)   # insert_one menambahkan _id walau gagal
            if key is not None:
                existing = db.orders.find_one({"user_id": user["_id"], "idem_key": key})
                if existing:
                    raise OrderReplay(existing)
    raise ApiError("Gagal membuat kode pesanan. Coba lagi.", 503)


def check_status_change(user, current_status, new_status):
    """Pastikan perubahan status diizinkan untuk role ini."""
    if user["role"] == "user":
        if (current_status, new_status) not in USER_TRANSITIONS:
            raise ApiError("Anda tidak dapat mengubah pesanan ke status tersebut", 403)
    elif new_status not in TRANSITIONS[current_status]:
        raise ApiError(f"Status tidak bisa berubah dari '{current_status}' ke '{new_status}'", 422)


def enforce_pending_limit(db, user):
    """Tolak pesanan baru bila pelanggan sudah punya terlalu banyak pesanan yang belum dibayar.

    Stok dipotong saat pesanan dibuat dan ditahan sampai pesanan dibayar atau kedaluwarsa, jadi tanpa
    batas ini satu akun bisa mengosongkan rak tanpa membayar. Memakai status 429, bukan 409, karena
    frontend menganggap 409 sebagai konflik stok dan memuat ulang katalog. Pengecekan ini tidak atomik:
    dua request bersamaan bisa melewati batas satu-dua pesanan, yang masih bisa diterima.
    """
    pending = db.orders.count_documents({"user_id": user["_id"], "status": "pending"})
    if pending >= MAX_PENDING_ORDERS:
        raise ApiError(
            f"Anda masih punya {pending} pesanan yang belum dibayar. "
            "Bayar atau batalkan salah satunya di menu Pesanan sebelum membuat yang baru.",
            429,
        )


@app.get("/api/orders")
@login_required
def orders_list():
    db = get_db()
    sweep_expired_orders(db)
    user = current_user()
    if user["role"] in STAFF_ROLES:
        # Pesanan yang masih berjalan harus selalu tampil, sebesar apa pun riwayatnya; kalau tidak,
        # pesanan yang sudah dibayar tapi belum dikirim bisa tergeser keluar dari 200 terbaru dan terlewat.
        # Batas ORDERS_LIMIT hanya berlaku untuk pesanan yang sudah selesai atau dibatalkan.
        open_orders = db.orders.find({"status": {"$in": list(OPEN_STATUS)}}).sort("created_at", -1).limit(OPEN_ORDERS_LIMIT)
        closed_orders = db.orders.find({"status": {"$nin": list(OPEN_STATUS)}}).sort("created_at", -1).limit(ORDERS_LIMIT)
        docs = sorted([*open_orders, *closed_orders], key=lambda o: o["created_at"], reverse=True)
    else:
        docs = db.orders.find({"user_id": user["_id"]}).sort("created_at", -1).limit(ORDERS_LIMIT)
    return jsonify({"orders": [serialize(o) for o in docs]})


@app.post("/api/orders")
@roles_required("user")
def orders_create():
    data = json_body()
    data["phone"] = re.sub(r"[\s.\-]", "", data["phone"]) if isinstance(data.get("phone"), str) else data.get("phone")
    form = Form(data)
    form.text("phone", "Nomor HP", 8, 16, regex=PHONE_RE, regex_msg=PHONE_ERROR)
    form.text("address", "Alamat pengiriman", 5, 200, multiline=True)
    form.text("note", "Catatan", 0, 200, required=False, multiline=True)
    clean = form.done()
    wanted = parse_cart_items(data.get("items"))
    expected_prices = parse_expected_prices(data["items"])
    key = idempotency_key()

    db = get_db()
    user = current_user()
    previous = replayed_order(db, user, key, wanted)
    if previous:   # request ulangan: kembalikan pesanan yang sudah ada, stok tidak dipotong lagi
        return jsonify({"order": serialize(previous), "replayed": True}), 200
    sweep_expired_orders(db)   # lepaskan stok pesanan kedaluwarsa sebelum menghitung ketersediaan
    enforce_pending_limit(db, user)
    reserved, lines = reserve_stock(db, wanted, expected_prices)
    try:
        now = utcnow()
        order = {"user_id": user["_id"], "username": user["username"],
                 "items": lines, "total": sum(line["subtotal"] for line in lines),
                 "phone": clean["phone"], "address": clean["address"], "note": clean["note"],
                 "status": "pending", "created_at": now, "updated_at": now,
                 "expires_at": now + timedelta(hours=PENDING_TTL_HOURS)}
        if key:
            order["idem_key"] = key
        insert_order(db, order, user, key)
    except OrderReplay as replay:   # request kembar yang berjalan bersamaan sudah menyimpan pesanannya
        release_stock(db, reserved)
        return jsonify({"order": serialize(replay.order), "replayed": True}), 200
    except Exception:
        release_stock(db, reserved)
        raise
    audit("pesanan_buat", f"{order['code']} total {order['total']}")
    return jsonify({"order": serialize(order)}), 201


@app.patch("/api/orders/<order_id>/status")
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
    check_status_change(user, current_status, new_status)
    now = utcnow()
    changes = {"status": new_status, "updated_at": now}
    if new_status == "paid":
        changes["paid_at"] = now   # dasar penghitungan pendapatan harian
    result = db.orders.update_one({"_id": target_id, "status": current_status}, {"$set": changes})
    if result.modified_count != 1:
        raise ApiError("Status pesanan sudah berubah. Muat ulang data.", 409)
    if new_status == "cancelled":
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
    audit("pesanan_status", f"{order['code']}: {current_status} -> {new_status}")
    return jsonify({"order": serialize(db.orders.find_one({"_id": target_id}))})


# --------------------------------------------------------------------------- #
# Routes: Dashboard, Pengguna, Log
# --------------------------------------------------------------------------- #
def order_summary(db):
    """Jumlah pesanan per status dan total pendapatan dari pesanan yang sudah dibayar."""
    by_status = {status: 0 for status in ORDER_STATUS}
    revenue = 0
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}, "sum": {"$sum": "$total"}}}]
    for row in db.orders.aggregate(pipeline):
        status = row["_id"]
        if status in by_status:
            by_status[status] = row["n"]
            if status in REVENUE_STATUS:
                revenue += row["sum"]
    return by_status, revenue


def today_summary(db):
    """Pesanan masuk (menurut tanggal dibuat) dan pendapatan (menurut tanggal dibayar) sejak 00:00 WIB hari ini.

    Pesanan lama yang dibayar sebelum `paid_at` ada tidak punya tanggal bayar; untuk mereka dipakai
    tanggal dibuat seperti sebelumnya.
    """
    local_now = utcnow() + WIB_OFFSET
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - WIB_OFFSET
    revenue = 0
    paid_today = {"$or": [{"paid_at": {"$gte": start}},
                          {"paid_at": {"$exists": False}, "created_at": {"$gte": start}}]}
    pipeline = [{"$match": {**paid_today, "status": {"$in": list(REVENUE_STATUS)}}},
                {"$group": {"_id": None, "sum": {"$sum": "$total"}}}]
    for row in db.orders.aggregate(pipeline):
        revenue = row["sum"]
    return {"orders": db.orders.count_documents({"created_at": {"$gte": start}}), "revenue": revenue}


@app.get("/api/stats")
@roles_required(*STAFF_ROLES)
def stats():
    db = get_db()
    sweep_expired_orders(db)
    by_status, revenue = order_summary(db)
    low_stock = (db[PRODUCT_COLLECTION].find({"stock": {"$lte": LOW_STOCK_LIMIT}}, NO_IMAGE)
                 .sort("stock", 1).limit(LOW_STOCK_LIST_SIZE))
    recent = db.orders.find().sort("created_at", -1).limit(RECENT_ORDERS_SIZE)
    result = {
        "revenue": revenue,
        "today": today_summary(db),
        "orders": {"total": sum(by_status.values()), **by_status},
        "products": db[PRODUCT_COLLECTION].count_documents({}),
        "low_stock": [product_json(p) for p in low_stock],
        "recent": [serialize(o) for o in recent],
        "users": None,
    }
    if current_user()["role"] == "master":
        result["users"] = {role: db.users.count_documents({"role": role}) for role in ROLES}
    return jsonify(result)


@app.get("/api/users")
@roles_required("master")
def users_list():
    docs = get_db().users.find().sort("created_at", 1).limit(USERS_LIMIT)
    return jsonify({"users": [serialize(u) for u in docs]})


@app.post("/api/users")
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


@app.patch("/api/users/<user_id>")
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
    if changes.get("active") is False:
        freed = cancel_pending_orders(db, target_id, "account_disabled")
        if freed:
            detail += f" ({freed} pesanan belum dibayar dibatalkan)"
    audit("user_ubah", detail)
    return jsonify({"user": serialize(db.users.find_one({"_id": target_id}))})


@app.delete("/api/users/<user_id>")
@roles_required("master")
def users_delete(user_id):
    target_id = object_id(user_id, "Pengguna")
    db = get_db()
    target = db.users.find_one({"_id": target_id})
    if not target:
        raise ApiError("Pengguna tidak ditemukan", 404)
    if target["_id"] == current_user()["_id"] or target["role"] == "master":
        raise ApiError("Akun master tidak dapat dihapus", 403)
    freed = cancel_pending_orders(db, target_id, "account_deleted")
    db.users.delete_one({"_id": target_id})
    audit("user_hapus", target["username"] + (f" ({freed} pesanan belum dibayar dibatalkan)" if freed else ""))
    return jsonify({"ok": True})


@app.get("/api/logs")
@roles_required("master")
def logs_list():
    # "log_hapus" tidak lagi dibuat, tapi baris lama (atau dari server berkode lama) tidak boleh tampil di daftar
    docs = get_db().logs.find({"action": {"$ne": "log_hapus"}}).sort("ts", -1).limit(LOGS_LIMIT)
    return jsonify({"logs": [serialize(log) for log in docs]})


@app.post("/api/logs/delete")
@roles_required("master")
def logs_delete():
    """Hapus satu atau beberapa log sekaligus (hanya master). Penghapusan tidak dicatat sebagai log baru."""
    ids = json_body().get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= LOGS_LIMIT:
        raise ApiError(f"Pilih 1 sampai {LOGS_LIMIT} log", 422)
    oids = list({object_id(item, "Log") for item in ids})
    result = get_db().logs.delete_many({"_id": {"$in": oids}})
    return jsonify({"deleted": result.deleted_count})


@app.get("/api/health")
def health():
    get_db().command("ping")
    return jsonify({"status": "ok"})


# --------------------------------------------------------------------------- #
# Akun master pertama
# --------------------------------------------------------------------------- #
def bootstrap(db):
    """Buat akun master dari environment variable bila belum ada master."""
    username, email = (_env_str(key) for key in ("MASTER_USERNAME", "MASTER_EMAIL"))
    password = _env_str("MASTER_PASSWORD", strip=False)   # password dipakai apa adanya
    if not (username and email and password):
        return
    try:
        if db.users.count_documents({"role": "master"}) == 0:
            db.users.insert_one(new_user_doc({
                "name": _env_str("MASTER_NAME", "Master")[:50],
                "username": username.strip().lower(),
                "email": email.strip().lower(),
                "password": password,
            }, "master"))
    except PyMongoError as exc:
        app.logger.error("Bootstrap gagal: %s", exc)


def create_master_cli():
    answers = {
        "name": input("Nama lengkap : "),
        "username": input("Username     : "),
        "email": input("Email        : "),
        "password": getpass.getpass("Password     : "),
    }
    try:
        clean = user_form(answers)
    except ApiError as e:
        for message in e.fields.values():
            print(f"  - {message}")
        sys.exit(1)
    try:
        get_db().users.insert_one(new_user_doc(clean, "master"))
    except DuplicateKeyError:
        print("Username atau email sudah terdaftar.")
        sys.exit(1)
    print(f"Akun master '{clean['username']}' dibuat.")


# --------------------------------------------------------------------------- #
# Data demo (simulasi multi user dan multi role)
# --------------------------------------------------------------------------- #
DEMO_PASSWORD = "demo12345"
DEMO_USERS = (
    ("Master Demo", "master_demo", "master", "master"),
    ("Admin Demo", "admin_demo", "admin", "admin"),
    ("Pelanggan Demo", "pelanggan_demo", "pelanggan", "user"),
)
DEMO_PRODUCTS = (
    ("Beras Premium 5kg", "Sembako", 72000, 40), ("Minyak Goreng 2L", "Sembako", 38000, 25),
    ("Telur Ayam 1kg", "Sembako", 31000, 18), ("Kopi Bubuk 200g", "Minuman", 24000, 12),
    ("Teh Celup 25 pcs", "Minuman", 9500, 4), ("Susu UHT 1L", "Minuman", 18500, 30),
    ("Sabun Cuci Piring", "Rumah Tangga", 14000, 22), ("Tisu Wajah", "Rumah Tangga", 12000, 3),
)


def seed_demo(db):
    """Isi akun demo (satu per role) dan contoh produk. Aman dijalankan berulang."""
    created = []
    for name, username, email_name, role in DEMO_USERS:
        if db.users.find_one({"username": username}):
            continue
        db.users.insert_one(new_user_doc({
            "name": name, "username": username, "email": f"{email_name}@tokobiru.test",
            "password": DEMO_PASSWORD}, role))
        created.append(username)
    if db[PRODUCT_COLLECTION].count_documents({}) == 0:
        now = utcnow()
        db[PRODUCT_COLLECTION].insert_many([
            {"name": n, "category": c, "price": p, "stock": st, "description": "",
             "created_at": now, "updated_at": now} for n, c, p, st in DEMO_PRODUCTS])
    return created


def seed_demo_cli():
    created = seed_demo(get_db())
    print("Akun demo (password semua: %s):" % DEMO_PASSWORD)
    for _, username, _, role in DEMO_USERS:
        print(f"  {role:<7} {username}" + ("" if username in created else "  (sudah ada)"))


# --------------------------------------------------------------------------- #
# Frontend (templates/index.html, static/style.css, static/app.js)
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return send_from_directory(TEMPLATE_DIR, "index.html", mimetype="text/html")


@app.get("/sw.js")
def service_worker():
    """Service worker harus disajikan dari akar situs agar cakupannya seluruh aplikasi (bukan hanya /static/).
    no-cache: browser selalu memeriksa versi terbaru, jadi pembaruan sampai ke pengguna setelah deploy."""
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-master":
        create_master_cli()
    elif len(sys.argv) > 1 and sys.argv[1] == "seed-demo":
        seed_demo_cli()
    else:
        app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
                debug=os.environ.get("FLASK_DEBUG") == "1")