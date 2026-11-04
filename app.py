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

Environment variable
    MONGO_URI     alamat MongoDB (wajib di Vercel; lokal default mongodb://localhost:27017)
    MONGO_DB      nama database (default: tokobiru)
    SECRET_KEY    string acak panjang (wajib di Vercel)
    MASTER_USERNAME / MASTER_EMAIL / MASTER_PASSWORD / MASTER_NAME
                  opsional: membuat akun master otomatis bila belum ada master
    PAY_INFO      opsional: instruksi pembayaran yang tampil di pesanan pelanggan
"""
import getpass
import os
import re
import secrets
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import wraps

from bson import ObjectId
from flask import Flask, Response, g, jsonify, request, send_from_directory, session
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

# --------------------------------------------------------------------------- #
# Konfigurasi
# --------------------------------------------------------------------------- #
IS_VERCEL = bool(os.environ.get("VERCEL"))
PAY_INFO = os.environ.get("PAY_INFO", "")[:200]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if IS_VERCEL:
        raise RuntimeError("SECRET_KEY belum diset di Environment Variables Vercel.")
    SECRET_KEY = "dev-only-secret-ganti-di-produksi"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_VERCEL,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=64 * 1024,
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
MAX_CART_LINES = 30
MAX_QTY_PER_PRODUCT = 99

# Login dan password
MAX_FAILED_LOGIN = 5
LOCK_MINUTES = 10
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128

# Batas jumlah data yang dikirim ke frontend
LOW_STOCK_LIMIT = 5        # stok <= angka ini dianggap menipis
LOW_STOCK_LIST_SIZE = 8
RECENT_ORDERS_SIZE = 5
PRODUCTS_LIMIT = 200
ORDERS_LIMIT = 200
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
    uri = os.environ.get("MONGO_URI")
    if uri:
        return uri
    if IS_VERCEL:
        raise RuntimeError("MONGO_URI belum diset di Environment Variables Vercel.")
    return "mongodb://localhost:27017"


def migrate_legacy_collections(db):
    """Pindahkan data dari collection lama `products` ke `master_product` (sekali saja)."""
    names = db.list_collection_names()
    if LEGACY_PRODUCT_COLLECTION in names and PRODUCT_COLLECTION not in names:
        db[LEGACY_PRODUCT_COLLECTION].rename(PRODUCT_COLLECTION)


def ensure_indexes(db):
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("email", ASCENDING)], unique=True)
    db[PRODUCT_COLLECTION].create_index([("name", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index([("category", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index([("stock", ASCENDING)])
    db.orders.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.logs.create_index([("ts", DESCENDING)])


def get_db():
    global _db
    if _db is not None:
        return _db
    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=6000, appname="tokobiru")
    db = client[os.environ.get("MONGO_DB", "tokobiru")]
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

NAME_ERROR = "Nama hanya boleh huruf, angka, spasi, titik, koma, apostrof, strip"
USERNAME_ERROR = "Username 3-20 karakter: huruf kecil, angka, underscore"
EMAIL_ERROR = "Format email tidak valid"


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
HIDDEN_FIELDS = ("password_hash", "failed", "locked_until")


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
    "font-src https://fonts.gstatic.com; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


def client_ip():
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.remote_addr or "")
    return sanitize(ip)[:45]


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid and OID_RE.fullmatch(str(uid)):
        user = get_db().users.find_one({"_id": ObjectId(uid)})
        if user and user.get("active", True):
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
        if not csrf_token_valid():
            raise ApiError("Token keamanan tidak valid. Muat ulang halaman.", 403)
        if not request.is_json:
            raise ApiError("Content-Type harus application/json", 415)


@app.after_request
def secure_headers(resp):
    resp.headers.update(SECURITY_HEADERS)
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif resp.mimetype == "text/html":
        resp.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return resp


# --------------------------------------------------------------------------- #
# Routes: Auth
# --------------------------------------------------------------------------- #
DUMMY_HASH = generate_password_hash(secrets.token_hex(8))


def start_session(user):
    session.clear()
    session.permanent = True
    session["uid"] = str(user["_id"])
    session["csrf"] = secrets.token_urlsafe(32)


def record_failed_login(db, user, now):
    """Tambah hitungan gagal login; kunci akun sementara bila sudah mencapai batas."""
    failed = user.get("failed", 0) + 1
    changes = {"failed": failed}
    if failed >= MAX_FAILED_LOGIN:
        changes = {"failed": 0, "locked_until": now + timedelta(minutes=LOCK_MINUTES)}
    db.users.update_one({"_id": user["_id"]}, {"$set": changes})


@app.get("/api/auth/me")
def auth_me():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    user = current_user()
    return jsonify({"user": public_user(user), "csrf": session["csrf"], "pay_info": PAY_INFO})


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
        raise ApiError(
            f"Akun dikunci sementara karena terlalu banyak percobaan. Coba lagi dalam {LOCK_MINUTES} menit.",
            429,
        )
    # Hash palsu tetap diperiksa agar waktu respons sama untuk akun yang tidak ada
    stored_hash = user["password_hash"] if user else DUMMY_HASH
    password_ok = check_password_hash(stored_hash, clean["password"])
    if user is None or not password_ok:
        if user:
            record_failed_login(db, user, now)
        audit("login_gagal", f"identifier={identifier[:40]}")
        raise ApiError("Username/email atau password salah", 401)
    if not user.get("active", True):
        raise ApiError("Akun Anda dinonaktifkan. Hubungi master.", 403)
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
    return form.done()


@app.get("/api/products")
@login_required
def products_list():
    db = get_db()
    search = sanitize(str(request.args.get("q", ""))[:50])
    category = sanitize(str(request.args.get("category", ""))[:30])
    query = {}
    if search:
        query["name"] = {"$regex": re.escape(search), "$options": "i"}
    if category:
        query["category"] = category
    docs = list(db[PRODUCT_COLLECTION].find(query).sort("name", 1).limit(PRODUCTS_LIMIT))
    categories = sorted(c for c in db[PRODUCT_COLLECTION].distinct("category") if isinstance(c, str))
    return jsonify({"products": [serialize(p) for p in docs], "categories": categories})


@app.post("/api/products")
@roles_required(*STAFF_ROLES)
def products_create():
    clean = product_form(json_body())
    clean["created_at"] = clean["updated_at"] = utcnow()
    db = get_db()
    result = db[PRODUCT_COLLECTION].insert_one(clean)
    audit("produk_tambah", clean["name"])
    return jsonify({"product": serialize(db[PRODUCT_COLLECTION].find_one({"_id": result.inserted_id}))}), 201


@app.put("/api/products/<product_id>")
@roles_required(*STAFF_ROLES)
def products_update(product_id):
    target_id = object_id(product_id, "Produk")
    clean = product_form(json_body())
    clean["updated_at"] = utcnow()
    db = get_db()
    result = db[PRODUCT_COLLECTION].update_one({"_id": target_id}, {"$set": clean})
    if result.matched_count == 0:
        raise ApiError("Produk tidak ditemukan", 404)
    audit("produk_ubah", clean["name"])
    return jsonify({"product": serialize(db[PRODUCT_COLLECTION].find_one({"_id": target_id}))})


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
def new_order_code():
    return "TB-" + utcnow().strftime("%y%m%d") + "-" + secrets.token_hex(2).upper()


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


def release_stock(db, reserved):
    """Kembalikan stok. `reserved` berisi pasangan (product_id, jumlah)."""
    for product_id, qty in reserved:
        db[PRODUCT_COLLECTION].update_one({"_id": product_id}, {"$inc": {"stock": qty}})


def reserve_stock(db, wanted):
    """Kurangi stok tiap produk secara atomik dan kembalikan (reserved, baris pesanan).

    Bila satu produk gagal, stok produk lain yang sudah dikurangi dikembalikan.
    """
    reserved, lines = [], []
    try:
        for product_id, qty in wanted.items():
            product = db[PRODUCT_COLLECTION].find_one({"_id": product_id})
            if not product:
                raise ApiError("Ada produk yang sudah tidak tersedia", 404)
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


def check_status_change(user, current_status, new_status):
    """Pastikan perubahan status diizinkan untuk role ini."""
    if user["role"] == "user":
        if (current_status, new_status) not in USER_TRANSITIONS:
            raise ApiError("Anda tidak dapat mengubah pesanan ke status tersebut", 403)
    elif new_status not in TRANSITIONS[current_status]:
        raise ApiError(f"Status tidak bisa berubah dari '{current_status}' ke '{new_status}'", 422)


@app.get("/api/orders")
@login_required
def orders_list():
    user = current_user()
    query = {} if user["role"] in STAFF_ROLES else {"user_id": user["_id"]}
    docs = get_db().orders.find(query).sort("created_at", -1).limit(ORDERS_LIMIT)
    return jsonify({"orders": [serialize(o) for o in docs]})


@app.post("/api/orders")
@roles_required("user")
def orders_create():
    data = json_body()
    form = Form(data)
    form.text("address", "Alamat pengiriman", 5, 200, multiline=True)
    form.text("note", "Catatan", 0, 200, required=False, multiline=True)
    clean = form.done()
    wanted = parse_cart_items(data.get("items"))

    db = get_db()
    user = current_user()
    reserved, lines = reserve_stock(db, wanted)
    try:
        now = utcnow()
        order = {"code": new_order_code(), "user_id": user["_id"], "username": user["username"],
                 "items": lines, "total": sum(line["subtotal"] for line in lines),
                 "address": clean["address"], "note": clean["note"], "status": "pending",
                 "created_at": now, "updated_at": now}
        db.orders.insert_one(order)
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
    result = db.orders.update_one({"_id": target_id, "status": current_status},
                                  {"$set": {"status": new_status, "updated_at": utcnow()}})
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


@app.get("/api/stats")
@roles_required(*STAFF_ROLES)
def stats():
    db = get_db()
    by_status, revenue = order_summary(db)
    low_stock = (db[PRODUCT_COLLECTION].find({"stock": {"$lte": LOW_STOCK_LIMIT}})
                 .sort("stock", 1).limit(LOW_STOCK_LIST_SIZE))
    recent = db.orders.find().sort("created_at", -1).limit(RECENT_ORDERS_SIZE)
    result = {
        "revenue": revenue,
        "orders": {"total": sum(by_status.values()), **by_status},
        "products": db[PRODUCT_COLLECTION].count_documents({}),
        "low_stock": [serialize(p) for p in low_stock],
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
    audit("user_ubah", f"{target['username']}: {changes}")
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
    db.users.delete_one({"_id": target_id})
    audit("user_hapus", target["username"])
    return jsonify({"ok": True})


@app.get("/api/logs")
@roles_required("master")
def logs_list():
    docs = get_db().logs.find().sort("ts", -1).limit(LOGS_LIMIT)
    return jsonify({"logs": [serialize(log) for log in docs]})


@app.get("/api/health")
def health():
    get_db().command("ping")
    return jsonify({"status": "ok"})


# --------------------------------------------------------------------------- #
# Akun master pertama
# --------------------------------------------------------------------------- #
def bootstrap(db):
    """Buat akun master dari environment variable bila belum ada master."""
    username, email, password = (
        os.environ.get(key) for key in ("MASTER_USERNAME", "MASTER_EMAIL", "MASTER_PASSWORD")
    )
    if not (username and email and password):
        return
    try:
        if db.users.count_documents({"role": "master"}) == 0:
            db.users.insert_one(new_user_doc({
                "name": os.environ.get("MASTER_NAME", "Master")[:50],
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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-master":
        create_master_cli()
    elif len(sys.argv) > 1 and sys.argv[1] == "seed-demo":
        seed_demo_cli()
    else:
        app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
                debug=os.environ.get("FLASK_DEBUG") == "1")