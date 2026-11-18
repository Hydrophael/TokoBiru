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
    QRIS_TTL_MINUTES   opsional: batas menit bayar khusus QRIS (default 60)
    XENDIT_SECRET_KEY      opsional: API key Xendit (xnd_development_... untuk uji, xnd_production_... untuk live).
                           Bila diisi bersama XENDIT_CALLBACK_TOKEN, QRIS asli aktif dan DUMMY_QRIS otomatis mati.
    XENDIT_CALLBACK_TOKEN  token verifikasi webhook (Dashboard Xendit > Settings > Webhooks). URL webhook: /webhooks/xendit
    MAX_PENDING_ORDERS opsional: jumlah pesanan belum dibayar yang boleh dimiliki satu pelanggan (default 3)
    SHIPPING_FEE  opsional: ongkos kirim flat dalam rupiah (default 10000; 0 = gratis)
    FREE_SHIPPING_MIN  opsional: belanja minimal untuk gratis ongkir (default 0 = tidak ada)
    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM
                  opsional: server email untuk kode reset password (port 587 STARTTLS, atau 465 SSL).
                  Tanpa SMTP_HOST dan pengirim (SMTP_FROM atau SMTP_USER), tombol "Lupa password" tidak tampil.
    VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT
                  opsional: notifikasi push pesanan untuk staf dan pelanggan (butuh paket pywebpush).
                  Buat kuncinya dengan: python app.py gen-vapid. VAPID_SUBJECT berisi mailto:emailanda@contoh.com
    Variabel yang dibiarkan kosong diperlakukan sama seperti tidak diisi (memakai nilai bawaan).
"""
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from functools import wraps
from html import escape as html_escape
from urllib.parse import urlsplit

from bson import ObjectId
from flask import (Flask, Response, g, has_request_context, jsonify, request,
                   send_from_directory, session)
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from proof_reader import ProofReadError, evaluate_proof, proof_fingerprint, read_transfer_proof

IS_VERCEL = bool(os.environ.get("VERCEL"))

if not IS_VERCEL:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _env_str(name, default="", strip=True):
    value = os.environ.get(name) or ""
    if not value.strip():
        return default
    return value.strip() if strip else value


PAY_INFO = _env_str("PAY_INFO")[:200]
# Baca bukti transfer otomatis oleh Gemini (saran untuk staf, bukan pengganti cek mutasi). Aktif bila GEMINI_API_KEY diisi.
GEMINI_API_KEY = _env_str("GEMINI_API_KEY")
PROOF_READER_MODEL = _env_str("PROOF_READER_MODEL", "gemini-3.5-flash-lite")
# Model cadangan bila model utama sibuk (HTTP 503) atau kuotanya habis (429). Kosongkan untuk mematikan cadangan.
PROOF_READER_FALLBACK_MODEL = _env_str("PROOF_READER_FALLBACK_MODEL", "gemini-3.1-flash-lite")
# Ciri rekening tujuan yang benar: 4 digit terakhir dan/atau nama pemilik, pisahkan dengan koma. Kosong = tujuan tidak diperiksa
PROOF_BANK_HINT = _env_str("PROOF_BANK_HINT")[:100]
PROOF_READER_ENABLED = bool(GEMINI_API_KEY)
# Batas pembacaan AI per akun per jam, supaya kuota/biaya tidak habis oleh unggah ulang berulang-ulang
PROOF_AUTO_READS_PER_HOUR = 10    # pelanggan (baca otomatis saat unggah; unggahan tetap berhasil walau kuota habis)
PROOF_STAFF_READS_PER_HOUR = 60   # staf (tombol baca manual)
PROOF_VERDICT_TEXT = {"match": "Cocok", "mismatch": "Tidak cocok", "suspicious": "Mencurigakan", "unclear": "Perlu dicek"}
SYSTEM_ACTOR = {"username": "sistem", "role": "-"}
# QRIS asli lewat Xendit. Bila key diisi, QRIS simulasi dimatikan supaya tidak ada jalan pintas "bayar gratis".
XENDIT_SECRET_KEY = _env_str("XENDIT_SECRET_KEY")
XENDIT_CALLBACK_TOKEN = _env_str("XENDIT_CALLBACK_TOKEN")
XENDIT_API_URL = "https://api.xendit.co"
XENDIT_API_VERSION = "2022-07-31"
XENDIT_ENABLED = bool(XENDIT_SECRET_KEY and XENDIT_CALLBACK_TOKEN)
XENDIT_TEST_MODE = XENDIT_SECRET_KEY.startswith("xnd_development")
# Hanya di sandbox: QR berisi tautan /pay/<token>; saat discan, server menyuruh Xendit mensimulasikan pembayaran
XENDIT_SIMULATE_SCAN = XENDIT_ENABLED and XENDIT_TEST_MODE
# Hanya untuk demo lokal: pelanggan bisa melunasi pesanannya sendiri tanpa uang
DUMMY_QRIS = _env_str("DUMMY_QRIS").lower() in ("1", "true", "ya", "on") and not XENDIT_SECRET_KEY
QRIS_ENABLED = XENDIT_ENABLED or DUMMY_QRIS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

SECRET_KEY = _env_str("SECRET_KEY")
if not SECRET_KEY:
    if IS_VERCEL:
        raise RuntimeError("SECRET_KEY belum diset di Environment Variables Vercel.")
    SECRET_KEY = "dev-only-secret-ganti-di-produksi"

MAX_JSON_BYTES = 64 * 1024
MAX_PRODUCT_BODY_BYTES = 1024 * 1024   # foto bukti transfer lebih besar (lihat PROOF_IMAGE_MAX_CHARS)
PRODUCT_WRITE_RE = re.compile(r"/api/products(?:/[0-9a-fA-F]{24})?")
PROFILE_WRITE_RE = re.compile(r"/api/auth/profile")
PROOF_WRITE_RE = re.compile(r"/api/orders/[0-9a-fA-F]{24}/proof")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_VERCEL,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=MAX_PRODUCT_BODY_BYTES,
)

ROLES = ("user", "admin", "master")
STAFF_ROLES = ("admin", "master")
ASSIGNABLE_ROLES = ("user", "admin")

ORDER_STATUS = ("pending", "paid", "shipped", "completed", "cancelled")
TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"shipped", "cancelled"},
    "shipped": {"completed", "cancelled"},   # dibatalkan setelah dikirim = retur; hanya staf (lihat USER_TRANSITIONS)
    "completed": set(),
    "cancelled": set(),
}
USER_TRANSITIONS = {("pending", "cancelled"), ("shipped", "completed")}
REVENUE_STATUS = ("paid", "shipped", "completed")
OPEN_STATUS = ("pending", "paid", "shipped")
CLOSED_STATUS = ("completed", "cancelled")
MAX_CART_LINES = 30
WIB_OFFSET = timedelta(hours=7)


def _env_int(name, default, minimum=1):
    try:
        return max(minimum, int(_env_str(name, str(default))))
    except ValueError:
        return default


PENDING_TTL_HOURS = _env_int("PENDING_TTL_HOURS", 24)
# Pesanan tunai (COD) menunggu toko memprosesnya, bukan menunggu pelanggan membayar. Batasnya dibuat lebih longgar supaya
# toko yang terlambat tidak membatalkan pesanan pelanggan, dan staf diingatkan COD_REMIND_HOURS jam sebelum batas habis.
COD_TTL_HOURS = _env_int("COD_TTL_HOURS", 72)
COD_REMIND_HOURS = _env_int("COD_REMIND_HOURS", 12)
QRIS_TTL_MINUTES = _env_int("QRIS_TTL_MINUTES", 60)
# Akurasi baca bukti: hasil yang menentukan dibaca dua kali oleh model berbeda dan baru dipercaya bila keduanya sama
PROOF_CONFIRM_READ = _env_str("PROOF_CONFIRM_READ", "1").lower() not in ("0", "false", "off", "tidak")
PROOF_CONFIRM_MIN_SECONDS = 3                                  # sisa waktu minimal agar bacaan kedua dicoba (saat unggah)
# Foto bukti berisi nama dan nomor rekening: dihapus otomatis sekian hari setelah diunggah (TTL MongoDB)
PROOF_RETENTION_DAYS = _env_int("PROOF_RETENTION_DAYS", 90)
# Unggah/ganti foto bukti per akun per jam. Terpisah dari batas pembacaan AI: ini melindungi penyimpanan dan beban server
PROOF_UPLOADS_PER_HOUR = 15
# Saat unggah, pembacaan dibatasi lebih pendek supaya unggahan pelanggan tidak kena batas waktu fungsi serverless.
# Pembacaan yang tidak sempat selesai tidak menggagalkan unggahan: admin membacanya saat membuka pesanan.
PROOF_UPLOAD_TIMEOUT = _env_int("PROOF_UPLOAD_TIMEOUT", 6, 3)
PROOF_STAFF_TIMEOUT = _env_int("PROOF_STAFF_TIMEOUT", 20, 5)   # tombol baca manual: berpikir lebih teliti, perlu waktu lebih
if PROOF_READER_ENABLED and not PROOF_BANK_HINT:
    print("PERINGATAN: GEMINI_API_KEY aktif tetapi PROOF_BANK_HINT kosong; rekening tujuan pada bukti transfer TIDAK diperiksa.",
          file=sys.stderr)
# Batas bayar tiap e-wallet (menit). Idealnya tidak lebih pendek dari umur tagihan di Xendit (ShopeePay 30 menit, DANA 24 jam),
# supaya tidak ada pembayaran masuk ke pesanan yang sudah dibatalkan. OVO mengabari Xendit saat tagihannya habis.
EWALLET_TTL_MINUTES = {
    "ewallet_dana": _env_int("DANA_TTL_MINUTES", 60),
    "ewallet_shopeepay": _env_int("SHOPEEPAY_TTL_MINUTES", 30),
    "ewallet_ovo": _env_int("OVO_TTL_MINUTES", 15),
}
# Alamat publik toko (mis. https://tokobiru.vercel.app): dipakai untuk tautan kembali dari e-wallet
PUBLIC_URL = _env_str("PUBLIC_URL").rstrip("/")
LOG_RETENTION_DAYS = _env_int("LOG_RETENTION_DAYS", 90)
MAX_PENDING_ORDERS = _env_int("MAX_PENDING_ORDERS", 3)
# Pesanan tunai (COD) dihitung terpisah: mereka menunggu toko, bukan menunggu pelanggan membayar
MAX_PENDING_COD = _env_int("MAX_PENDING_COD_ORDERS", 5)
# Bukti transfer yang belum dicek staf sekian jam: staf diingatkan sekali (pesanan bukti tidak kedaluwarsa sendiri)
PROOF_REMIND_HOURS = _env_int("PROOF_REMIND_HOURS", 12)
SHIPPING_FEE = _env_int("SHIPPING_FEE", 10000, minimum=0)
FREE_SHIPPING_MIN = _env_int("FREE_SHIPPING_MIN", 0, minimum=0)
SHIPPING_METHODS = ("delivery", "pickup")
# E-wallet lewat Xendit: kode metode di toko -> kode kanal di Xendit
EWALLET_CHANNELS = {"ewallet_dana": "ID_DANA", "ewallet_shopeepay": "ID_SHOPEEPAY", "ewallet_ovo": "ID_OVO"}
# Transfer bank hanya ditawarkan bila PAY_INFO (rekening tujuan) terisi: tanpa itu pelanggan tidak tahu harus transfer ke mana
PAYMENT_METHODS = (((("transfer",) if PAY_INFO else ()) + ("cash",)) + (("qris",) if QRIS_ENABLED else ())
                   + (tuple(EWALLET_CHANNELS) if XENDIT_ENABLED else ()))
if not PAY_INFO:
    print("PERINGATAN: PAY_INFO kosong; transfer bank tidak ditawarkan ke pelanggan. Isi rekening tujuan untuk mengaktifkannya.",
          file=sys.stderr)
EXPIRE_SWEEP_SECONDS = 60
EXPIRE_BATCH = 50
MAX_QTY_PER_PRODUCT = 99

MAX_FAILED_LOGIN = 5
LOCK_MINUTES = 10
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128

SMTP_HOST = _env_str("SMTP_HOST")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = _env_str("SMTP_USER")
SMTP_PASSWORD = _env_str("SMTP_PASSWORD", strip=False)
SMTP_FROM = _env_str("SMTP_FROM", SMTP_USER)
SMTP_TIMEOUT = 8
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_FROM)
RESET_CODE_LENGTH = 6
RESET_CODE_MINUTES = 15
RESET_COOLDOWN_SECONDS = 60
MAX_RESET_ATTEMPTS = 5
RESET_LOCK_MINUTES = 10

LOW_STOCK_LIMIT = 5
LOW_STOCK_LIST_SIZE = 8
RECENT_ORDERS_SIZE = 5
PRODUCTS_LIMIT = 1000
ORDERS_LIMIT = 200
OPEN_ORDERS_LIMIT = 1000
USERS_LIMIT = 500
LOGS_LIMIT = 150

_db = None

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
    names = db.list_collection_names()
    if LEGACY_PRODUCT_COLLECTION in names and PRODUCT_COLLECTION not in names:
        db[LEGACY_PRODUCT_COLLECTION].rename(PRODUCT_COLLECTION)


def ensure_unique_order_code_index(db):
    # Kode pesanan dipakai sebagai referensi bayar, jadi harus unik
    try:
        db.orders.create_index([("code", ASCENDING)], unique=True)
    except OperationFailure as exc:
        app.logger.error("Indeks unik orders.code gagal dibuat (ada kode ganda di data lama?): %s", exc)


def ensure_ttl_index(coll, field, days, name):
    """Indeks TTL (dokumen terhapus otomatis `days` hari setelah `field`). Bila lama simpan diubah lewat .env, indeks lama diperbarui."""
    seconds = days * 86400
    try:
        coll.create_index([(field, ASCENDING)], expireAfterSeconds=seconds, name=name)
    except OperationFailure:
        try:
            coll.database.command("collMod", coll.name, index={"name": name, "expireAfterSeconds": seconds})
        except PyMongoError as exc:
            app.logger.error("Indeks TTL %s gagal diperbarui: %s", name, exc)


def ensure_indexes(db):
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("email", ASCENDING)], unique=True)
    db[PRODUCT_COLLECTION].create_index([("name", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index([("category", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index([("stock", ASCENDING)])
    db[PRODUCT_COLLECTION].create_index(
        [("name", "text"), ("category", "text"), ("description", "text")],
        weights={"name": 5, "category": 2, "description": 1},
        default_language="none",
        name="product_text",
    )
    db.orders.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.orders.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
    db.orders.create_index([("created_at", DESCENDING)])
    db.orders.create_index([("paid_at", DESCENDING)])
    db.orders.create_index([("user_id", ASCENDING), ("idem_key", ASCENDING)], unique=True,
                           partialFilterExpression={"idem_key": {"$type": "string"}})
    ensure_unique_order_code_index(db)
    db.logs.create_index([("ts", DESCENDING)])
    db.logs.create_index([("ts", ASCENDING)], expireAfterSeconds=LOG_RETENTION_DAYS * 86400, name="logs_ttl")
    db.rate_limits.create_index([("expires", ASCENDING)], expireAfterSeconds=0, name="rate_ttl")
    db.push_subs.create_index([("user_id", ASCENDING)])
    db.order_proofs.create_index([("sha256", ASCENDING)])
    ensure_ttl_index(db.order_proofs, "uploaded_at", PROOF_RETENTION_DAYS, "proof_ttl")
    db.orders.create_index([("proof_check.reference", ASCENDING)], sparse=True)
    db.orders.create_index([("proof_check.fingerprint", ASCENDING)], sparse=True)
    db.notifications.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.notifications.create_index([("created_at", ASCENDING)], expireAfterSeconds=30 * 86400, name="notif_ttl")


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
    return jsonify({"error": "Data yang dikirim terlalu besar"}), 413


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code
    app.logger.exception("Unhandled error")
    return jsonify({"error": "Terjadi kesalahan pada server"}), 500


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


IMAGE_MAX_CHARS = 300_000
PROOF_IMAGE_MAX_CHARS = 700_000   # bukti transfer: angka kecil di struk butuh resolusi lebih tinggi daripada foto produk
IMAGE_RE = re.compile(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})")


def decode_image(raw, max_chars=IMAGE_MAX_CHARS):
    if len(raw) > max_chars:
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
        if not isinstance(raw, str):
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

    def image(self, name="image", label="Foto", max_chars=IMAGE_MAX_CHARS):
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
            self.out[name] = decode_image(raw, max_chars)
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
        raise ApiError("Data yang dikirim tidak terbaca. Muat ulang halaman lalu coba lagi.", 400)
    return data


def object_id(value, label="ID"):
    if not isinstance(value, str) or not OID_RE.fullmatch(value):
        raise ApiError(f"{label} tidak valid", 400)
    return ObjectId(value)


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


def public_user(user):
    if not user:
        return None
    out = {"id": str(user["_id"]), "username": user["username"], "name": user["name"],
           "email": user["email"], "role": user["role"]}
    if user.get("image_v"):
        out["photo"] = f"/api/auth/avatar?v={int(user['image_v'])}"
    if user["role"] == "user":
        out["addresses"] = [address_json(item) for item in user.get("addresses", [])]
    if PUSH_ENABLED:
        out["push_key"] = VAPID_PUBLIC_KEY   # admin, master, dan pelanggan boleh berlangganan notifikasi
    return out


def user_form(data, with_role=False):
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


ADDRESS_LIMIT = 5
ADDRESS_LABELS = ("Rumah", "Kantor", "Kos", "Lainnya")


def address_json(item):
    return {"id": item["id"], "label": item["label"], "recipient": item["recipient"],
            "phone": item["phone"], "address": item["address"], "main": bool(item.get("main"))}


def address_form(data):
    data = dict(data)
    if isinstance(data.get("phone"), str):
        data["phone"] = re.sub(r"[\s.\-]", "", data["phone"])
    form = Form(data)
    form.choice("label", "Label alamat", ADDRESS_LABELS)
    form.text("recipient", "Nama penerima", 2, 50, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.text("phone", "Nomor HP", 8, 16, regex=PHONE_RE, regex_msg=PHONE_ERROR)
    form.text("address", "Alamat pengiriman", 5, 200, multiline=True)
    clean = form.done()
    clean["main"] = data.get("main") is True
    return clean


def save_addresses(db, user, addresses):
    if addresses and not any(item.get("main") for item in addresses):
        addresses[0]["main"] = True
    db.users.update_one({"_id": user["_id"]}, {"$set": {"addresses": addresses}})
    return [address_json(item) for item in addresses]


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
# Tanpa script inline; script hanya boleh dari domain sendiri
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


@app.before_request
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


@app.after_request
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


# --- Notifikasi push (Web Push) untuk staf dan pelanggan ---
try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pywebpush belum terpasang: fitur mati, aplikasi tetap jalan
    webpush = None
    WebPushException = Exception  # type: ignore[misc,assignment]

VAPID_PUBLIC_KEY = _env_str("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = _env_str("VAPID_PRIVATE_KEY")


# Bentuk yang diterima layanan push: mailto:nama@domain.com atau alamat https://
_SUBJECT_OK = re.compile(r"^mailto:[^@\s]+@[^@\s]+\.[^@\s]+$|^https://\S+$", re.I)


def _vapid_subject():
    explicit = _env_str("VAPID_SUBJECT").strip("'\" ")
    if explicit and "@" in explicit and not explicit.lower().startswith(("mailto:", "http")):
        explicit = "mailto:" + explicit   # email tanpa awalan: lengkapi otomatis
    if explicit and _SUBJECT_OK.match(explicit):
        return explicit
    if explicit:
        app.logger.warning("VAPID_SUBJECT tidak valid (%r), dipakai nilai cadangan. Isi dengan mailto:emailanda@gmail.com", explicit)
    if PUBLIC_URL.startswith("https://"):
        return PUBLIC_URL
    return "mailto:" + (SMTP_USER if _SUBJECT_OK.match("mailto:" + SMTP_USER) else "admin@example.com")


VAPID_SUBJECT = _vapid_subject()
PUSH_ENABLED = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and webpush)
PUSH_MAX_DEVICES_PER_USER = 5
PUSH_MAX_SUBS = 200
PUSH_TIMEOUT = 3
PUSH_BUDGET = 4   # detik: total waktu menunggu semua perangkat, supaya respons ke pelanggan tidak tertahan push yang lambat
# Server hanya boleh menghubungi layanan push milik browser, supaya alamat buatan pengguna tidak bisa dipakai menyerang jaringan dalam
PUSH_HOST_SUFFIXES = ("googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")
PUSH_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{8,200}={0,2}")
PAYMENT_NAME = {"transfer": "Transfer", "cash": "Bayar di tempat", "qris": "QRIS",
                "ewallet_dana": "DANA", "ewallet_shopeepay": "ShopeePay", "ewallet_ovo": "OVO"}


def require_push_enabled():
    if not PUSH_ENABLED:
        raise ApiError("Notifikasi belum diaktifkan di toko ini.", 503)


def push_endpoint_ok(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 700:
        return False
    try:
        parts = urlsplit(endpoint)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and not parts.username and port in (None, 443)
            and any(host == suffix or host.endswith("." + suffix) for suffix in PUSH_HOST_SUFFIXES))


def push_message(title, body, tag, view="orders"):
    return json.dumps({"title": title, "body": body, "tag": tag, "url": f"/?buka={view}"})


def _push_one(sub, payload):
    """True = terkirim, False = perangkat sudah tidak berlangganan (hapus), None = gagal sementara."""
    if webpush is None:
        return None
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": VAPID_SUBJECT},
                ttl=3600, timeout=PUSH_TIMEOUT)
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return False
        app.logger.warning("Push gagal (HTTP %s): %s", status, str(exc)[:200])
    except Exception as exc:
        app.logger.warning("Push gagal: %s", str(exc)[:200])
    return None


def deliver_push(db, subs, payload):
    """Kirim ke semua perangkat di `subs`; perangkat yang sudah tidak berlangganan dihapus. Mengembalikan jumlah terkirim."""
    if not subs:
        return 0
    pool = ThreadPoolExecutor(max_workers=min(16, len(subs)))
    futures = [pool.submit(_push_one, sub, payload) for sub in subs]
    try:
        wait(futures, timeout=PUSH_BUDGET)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)   # yang belum selesai ditinggalkan; bukan alasan menahan respons
    results = [future.result() if future.done() and not future.cancelled() and future.exception() is None else None
               for future in futures]
    gone = [sub["_id"] for sub, ok in zip(subs, results) if ok is False]
    if gone:
        db.push_subs.delete_many({"_id": {"$in": gone}})
    return sum(1 for ok in results if ok)


def record_notification(db, user_ids, title, body, tag, view="orders"):
    """Simpan kabar ke pusat notifikasi di dalam aplikasi (lonceng di header). Kabar yang sama (akun + tag) tidak dobel,
    tetapi bila terjadi lagi (mis. bukti transfer diganti) kabar itu diperbarui: isinya diganti, tanda baca dihapus, dan naik ke atas."""
    if not user_ids:
        return
    now = utcnow()
    db.notifications.bulk_write([
        UpdateOne({"user_id": uid, "tag": tag},
                  {"$set": {"title": title, "body": body, "read": False, "created_at": now},
                   "$setOnInsert": {"user_id": uid, "tag": tag, "view": view}}, upsert=True)
        for uid in user_ids], ordered=False)


def push_staff(title, body, tag, view="orders"):
    """Beri kabar ke semua staf (admin/master) di lonceng aplikasi dan, bila aktif, di perangkat mereka. Tidak pernah menggagalkan alur pesanan."""
    try:
        db = get_db()
        staff = [u["_id"] for u in db.users.find({"role": {"$in": list(STAFF_ROLES)}, "active": {"$ne": False}}, {"_id": 1})]
        record_notification(db, staff, title, body, tag, view)
        if not PUSH_ENABLED:
            return
        subs = list(db.push_subs.find({"user_id": {"$in": staff}}).limit(PUSH_MAX_SUBS))
        deliver_push(db, subs, push_message(title, body, tag, view))
    except Exception as exc:
        app.logger.warning("Push ke staf gagal: %s", exc)


def push_user(user_id, title, body, tag, view="orders"):
    """Beri kabar ke satu akun (mis. pelanggan pemilik pesanan): di lonceng aplikasi dan, bila aktif, di semua perangkatnya. Tidak pernah menggagalkan alur pesanan."""
    try:
        db = get_db()
        record_notification(db, [user_id], title, body, tag, view)
        if not PUSH_ENABLED:
            return
        subs = list(db.push_subs.find({"user_id": user_id}).limit(PUSH_MAX_DEVICES_PER_USER))
        deliver_push(db, subs, push_message(title, body, tag, view))
    except Exception as exc:
        app.logger.warning("Push ke pengguna gagal: %s", exc)


# Kabar untuk pelanggan: status -> (judul, isi)
CUSTOMER_PUSH = {
    "paid": lambda code: ("Pembayaran diterima", f"Pesanan {code} sudah dibayar dan sedang disiapkan."),
    "shipped": lambda code: ("Pesanan dikirim", f"Pesanan {code} sedang diantar. Mohon siap menerima."),
    "cancelled": lambda code: ("Pesanan dibatalkan", f"Pesanan {code} dibatalkan oleh toko. Hubungi toko bila ada pertanyaan."),
}


def customer_push(status, order, refund=False):
    """Kabar untuk pelanggan: sama dengan CUSTOMER_PUSH, tetapi pesanan ambil di toko tidak diantar dan pembatalan yang perlu refund menyebutnya."""
    code = order["code"]
    if status == "shipped" and order.get("shipping_method") == "pickup":
        cash = f" Siapkan uang tunai {format_rupiah(order['total'])}." if order.get("cod") else ""
        return "Pesanan siap diambil", f"Pesanan {code} sudah siap diambil di toko.{cash} Tunjukkan kode pesanan saat mengambil."
    if status == "cancelled" and refund:
        return "Pesanan dibatalkan", f"Pesanan {code} dibatalkan oleh toko. Dana Anda akan dikembalikan; hubungi toko bila ada pertanyaan."
    return CUSTOMER_PUSH[status](code)


@app.post("/api/push/subscribe")
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


@app.post("/api/push/unsubscribe")
@login_required
def push_unsubscribe():
    endpoint = json_body().get("endpoint")
    if isinstance(endpoint, str) and len(endpoint) <= 700:
        sub_id = hashlib.sha256(endpoint.encode()).hexdigest()
        get_db().push_subs.delete_one({"_id": sub_id, "user_id": current_user()["_id"]})
    return jsonify({"ok": True})


def notification_json(doc):
    return {"id": str(doc["_id"]), "title": doc.get("title", ""), "body": doc.get("body", ""),
            "view": doc.get("view", "orders"), "read": bool(doc.get("read")),
            "created_at": doc["created_at"].isoformat() + "Z"}


@app.get("/api/notifications")
@login_required
def notifications_list():
    db = get_db()
    uid = current_user()["_id"]
    docs = list(db.notifications.find({"user_id": uid}).sort("created_at", -1).limit(30))
    unread = db.notifications.count_documents({"user_id": uid, "read": False})
    resp = jsonify({"items": [notification_json(doc) for doc in docs], "unread": unread})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/notifications/read")
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


DUMMY_HASH = generate_password_hash(secrets.token_hex(8))


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


@app.get("/api/auth/me")
def auth_me():
    user = current_user()
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"user": public_user(user), "csrf": session["csrf"], "pay_info": PAY_INFO,
                    "dummy_qris": DUMMY_QRIS, "qris_enabled": QRIS_ENABLED, "ewallet_enabled": XENDIT_ENABLED, "qris_minutes": QRIS_TTL_MINUTES,
                    "ewallet_minutes": EWALLET_TTL_MINUTES, "proof_reader": PROOF_READER_ENABLED, "proof_retention_days": PROOF_RETENTION_DAYS,
                    "server_time": utcnow().isoformat() + "Z", "reset_enabled": EMAIL_ENABLED,
                    "shipping": {"fee": SHIPPING_FEE, "free_min": FREE_SHIPPING_MIN}})


@app.post("/api/auth/register")
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


@app.post("/api/auth/login")
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
    stored_hash = user["password_hash"] if user else DUMMY_HASH
    password_ok = check_password_hash(stored_hash, clean["password"])
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


@app.post("/api/auth/logout")
def auth_logout():
    if session.get("uid"):
        endpoint = (request.get_json(silent=True) or {}).get("endpoint")
        try:
            user = current_user()
            if user and isinstance(endpoint, str) and len(endpoint) <= 700:
                # Perangkat ini dilepas dari akun supaya akun lain di perangkat yang sama tidak menerima kabar toko
                get_db().push_subs.delete_one({"_id": hashlib.sha256(endpoint.encode()).hexdigest(), "user_id": user["_id"]})
        except PyMongoError as exc:
            app.logger.warning("Langganan push gagal dilepas saat keluar: %s", exc)
        audit("logout", "")
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"ok": True, "csrf": session["csrf"]})


@app.patch("/api/auth/profile")
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


@app.get("/api/auth/avatar")
@login_required
def auth_avatar():
    user = current_user()
    if not user.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(user["image"]), mimetype=user.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@app.post("/api/auth/addresses")
@roles_required("user")
def addresses_create():
    clean = address_form(json_body())
    db = get_db()
    user = current_user()
    addresses = list(user.get("addresses", []))
    if len(addresses) >= ADDRESS_LIMIT:
        raise ApiError(f"Maksimal {ADDRESS_LIMIT} alamat. Hapus salah satu dulu.", 409)
    first = not addresses
    if clean["main"] or first:
        for item in addresses:
            item["main"] = False
    addresses.append({"id": secrets.token_hex(6), "label": clean["label"], "recipient": clean["recipient"],
                      "phone": clean["phone"], "address": clean["address"], "main": clean["main"] or first})
    saved = save_addresses(db, user, addresses)
    audit("alamat_ubah", f"alamat {clean['label']} ditambah")
    return jsonify({"addresses": saved}), 201


def find_address(addresses, address_id):
    for item in addresses:
        if item["id"] == address_id:
            return item
    raise ApiError("Alamat tidak ditemukan", 404)


@app.put("/api/auth/addresses/<address_id>")
@roles_required("user")
def addresses_update(address_id):
    clean = address_form(json_body())
    db = get_db()
    user = current_user()
    addresses = list(user.get("addresses", []))
    target = find_address(addresses, address_id)
    if clean["main"]:
        for item in addresses:
            item["main"] = False
    target.update({"label": clean["label"], "recipient": clean["recipient"], "phone": clean["phone"],
                   "address": clean["address"], "main": clean["main"] or bool(target.get("main"))})
    saved = save_addresses(db, user, addresses)
    audit("alamat_ubah", f"alamat {clean['label']} diubah")
    return jsonify({"addresses": saved})


@app.delete("/api/auth/addresses/<address_id>")
@roles_required("user")
def addresses_delete(address_id):
    db = get_db()
    user = current_user()
    addresses = list(user.get("addresses", []))
    target = find_address(addresses, address_id)
    addresses = [item for item in addresses if item is not target]
    if target.get("main") and addresses:
        addresses[0]["main"] = True
    saved = save_addresses(db, user, addresses)
    audit("alamat_ubah", f"alamat {target['label']} dihapus")
    return jsonify({"addresses": saved})


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
        raise ApiError(f"Ganti password dikunci sementara karena terlalu banyak percobaan. Coba lagi dalam {LOCK_MINUTES} menit.", 429)
    if not check_password_hash(user["password_hash"], clean["current_password"]):
        record_failed_login(db, user, now)
        login_failed(user, client_ip())
        audit("password_gagal", "password lama salah")
        raise ApiError("Password lama salah", 422, {"current_password": "Password lama salah"})
    if clean["new_password"] == clean["current_password"]:
        message = "Password baru harus berbeda dari yang lama"
        raise ApiError(message, 422, {"new_password": message})
    db.users.update_one({"_id": user["_id"]}, {
        "$set": {"password_hash": generate_password_hash(clean["new_password"]),
                 "failed": 0, "locked_until": None},
        "$inc": {"session_version": 1}})
    session["sv"] = db.users.find_one({"_id": user["_id"]}).get("session_version", 1)
    audit("password_ubah", "sesi di perangkat lain dikeluarkan")
    return jsonify({"ok": True})


RESET_FIELDS = {"reset_code_hash": "", "reset_expires": "", "reset_sent_at": ""}
RESET_GUARD_FIELDS = {"reset_failed": "", "reset_locked_until": ""}


def send_email(to, subject, body, html=None, inline_images=None):
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
    try:
        with open(EMAIL_LOGO_FILE, "rb") as f:
            return f.read()
    except OSError:
        return None


def reset_email_html(name, code, logo_cid=None):
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


@app.post("/api/auth/forgot")
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
            app.logger.error("Gagal mengirim email reset password: %s", exc)
            db.users.update_one({"_id": user["_id"]}, {"$unset": RESET_FIELDS})
        else:
            audit("reset_minta", "kode dikirim ke email", user)
    return jsonify({"ok": True, "retry_after": RESET_COOLDOWN_SECONDS, "expires_minutes": RESET_CODE_MINUTES})


@app.post("/api/auth/reset")
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
            {"$set": {"password_hash": generate_password_hash(clean["new_password"]),
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


@app.post("/api/auth/reset/check")
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


def product_form(data):
    form = Form(data)
    form.text("name", "Nama produk", 2, 80)
    form.text("category", "Kategori", 2, 30)
    form.integer("price", "Harga", 100, 100_000_000)
    form.integer("stock", "Stok", 0, 100_000)
    form.text("description", "Deskripsi", 0, 300, required=False, multiline=True)
    form.image("image", "Foto produk")
    return form.done()


NO_IMAGE = {"image": 0}


def product_json(doc):
    out = serialize(doc)
    if doc.get("image_v"):
        out["photo"] = f"/api/products/{out['id']}/image?v={int(doc['image_v'])}"
    return out


def split_image(clean):
    if "image" not in clean:
        return {}, {}
    image = clean.pop("image")
    if image is None:
        return {}, {"image": "", "image_type": "", "image_v": ""}
    data, mime = image
    return {"image": data, "image_type": mime, "image_v": int(time.time() * 1000)}, {}


def text_search_term(search):
    words = (word.replace('"', "").replace("\\", "").lstrip("-") for word in search.split())
    return " ".join(word for word in words if word)


def search_products(db, search, category):
    collection = db[PRODUCT_COLLECTION]
    base = {"category": category} if category else {}
    term = text_search_term(search)
    if term:
        text_query = {**base, "$text": {"$search": term}}
        try:
            docs = list(collection.find(text_query, {"_score": {"$meta": "textScore"}, **NO_IMAGE})
                        .sort([("_score", {"$meta": "textScore"})]).limit(PRODUCTS_LIMIT))
        except OperationFailure as exc:
            app.logger.warning("Pencarian teks gagal, memakai regex: %s", exc)
            docs = []
        if docs:
            for doc in docs:
                doc.pop("_score", None)
            return docs, text_query
    regex_query = {**base, "name": {"$regex": re.escape(search), "$options": "i"}}
    docs = list(collection.find(regex_query, NO_IMAGE).sort("name", 1).limit(PRODUCTS_LIMIT))
    return docs, regex_query


@app.get("/api/products")
@login_required
def products_list():
    db = get_db()
    sweep_expired_orders(db)
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
            query["stock"] = {"$gte": -delta}

    # Dokumen sebelum diubah dibawa pulang oleh perintah yang sama, jadi harga lama yang dicatat pasti harga yang tergantikan
    before = collection.find_one_and_update(query, update, projection={"price": 1}, return_document=ReturnDocument.BEFORE)
    if before is None:
        if not collection.find_one({"_id": target_id}):
            raise ApiError("Produk tidak ditemukan", 404)
        raise ApiError("Stok berubah karena ada penjualan. Muat ulang halaman lalu coba lagi.", 409)
    old_price, new_price = before.get("price"), clean.get("price")
    price_note = (f" (harga {format_rupiah(old_price)} → {format_rupiah(new_price)})"
                  if isinstance(old_price, int) and isinstance(new_price, int) and old_price != new_price else "")
    photo_note = " (foto diganti)" if image_set else " (foto dihapus)" if image_unset else ""
    audit("produk_ubah", clean["name"] + (f" (stok {delta:+d})" if delta else "") + price_note + photo_note)
    return jsonify({"product": product_json(collection.find_one({"_id": target_id}, NO_IMAGE))})


@app.get("/api/products/<product_id>/image")
@login_required
def products_image(product_id):
    target_id = object_id(product_id, "Produk")
    doc = get_db()[PRODUCT_COLLECTION].find_one({"_id": target_id}, {"image": 1, "image_type": 1})
    if not doc or not doc.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(doc["image"]), mimetype=doc.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
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


ORDER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ORDER_CODE_LENGTH = 6
ORDER_CODE_ATTEMPTS = 5
IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{8,64}")


def new_order_code():
    suffix = "".join(secrets.choice(ORDER_CODE_ALPHABET) for _ in range(ORDER_CODE_LENGTH))
    return "TB-" + utcnow().strftime("%y%m%d") + "-" + suffix


def parse_cart_items(items):
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
    for product_id, qty in reserved:
        db[PRODUCT_COLLECTION].update_one({"_id": product_id}, {"$inc": {"stock": qty}})


_last_sweep = None


def is_overdue(order):
    # Transfer yang sudah ada buktinya tidak kedaluwarsa sendiri: uangnya mungkin sudah masuk, jadi stafflah yang memutuskan
    expires = order.get("expires_at")
    return bool(order.get("status") == "pending" and expires and expires <= utcnow() and not order.get("proof_at"))


def cancel_expired_order(db, order, reason="expired", audit_action="pesanan_kedaluwarsa"):
    # Atomik: hanya pesanan yang masih pending yang dibatalkan, stok dikembalikan sekali saja
    query = {"_id": order["_id"], "status": "pending"}
    if reason == "expired":
        query["proof_at"] = None   # bukti bisa saja baru diunggah setelah pesanan dibaca: jangan dibatalkan
    result = db.orders.update_one(
        query,
        {"$set": {"status": "cancelled", "cancel_reason": reason, "updated_at": utcnow()}})
    if result.modified_count != 1:
        return False
    release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
    audit(audit_action, order["code"], {"username": "sistem", "role": "-"})
    why = ("karena pembayaran gagal atau ditolak" if reason == "payment_failed" else "karena melewati batas waktu bayar")
    try:
        record_notification(db, [order["user_id"]], "Pesanan dibatalkan", f"Pesanan {order['code']} dibatalkan otomatis {why}.",
                            f"my-{order['code']}-batal")
    except PyMongoError as exc:
        app.logger.warning("Kabar pembatalan otomatis gagal disimpan: %s", exc)
    return True


def settle_overdue(db, order):
    # Batas bayar dicek per pesanan agar hitung mundur di layar tepat, tidak menunggu penyapuan berkala
    if order and is_overdue(order):
        cancel_expired_order(db, order)
        return db.orders.find_one({"_id": order["_id"]}) or order
    return order


def remind_cod_orders(db, now):
    # Pesanan tunai yang hampir kedaluwarsa: staf diingatkan sekali supaya sempat memproses atau membatalkannya sendiri
    due = db.orders.find({"status": "pending", "cod": True, "remind_sent": {"$ne": True},
                          "expires_at": {"$gt": now, "$lte": now + timedelta(hours=COD_REMIND_HOURS)}}).limit(EXPIRE_BATCH)
    for order in list(due):
        claimed = db.orders.update_one({"_id": order["_id"], "status": "pending", "remind_sent": {"$ne": True}},
                                       {"$set": {"remind_sent": True}})
        if claimed.modified_count != 1:
            continue   # permintaan lain sudah mengingatkan
        deadline = (order["expires_at"] + WIB_OFFSET).strftime("%d/%m %H:%M")
        push_staff("Pesanan tunai belum diproses",
                   f"{order['code']} · {format_rupiah(order['total'])} akan dibatalkan otomatis {deadline} WIB. Proses atau batalkan sebelum itu.",
                   f"order-{order['code']}-ingat")


def remind_proof_orders(db, now):
    # Transfer yang sudah ada buktinya tidak kedaluwarsa sendiri, jadi stok dan jatah pesanan pelanggan tertahan sampai staf bertindak.
    # Staf diingatkan sekali setelah PROOF_REMIND_HOURS jam supaya pesanan tidak terlupakan.
    due = db.orders.find({"status": "pending", "proof_remind_sent": {"$ne": True},
                          "proof_at": {"$lte": now - timedelta(hours=PROOF_REMIND_HOURS)}}).limit(EXPIRE_BATCH)
    for order in list(due):
        claimed = db.orders.update_one({"_id": order["_id"], "status": "pending", "proof_remind_sent": {"$ne": True}},
                                       {"$set": {"proof_remind_sent": True}})
        if claimed.modified_count != 1:
            continue   # permintaan lain sudah mengingatkan
        push_staff("Bukti transfer belum dicek",
                   f"{order['code']} · {format_rupiah(order['total'])}: bukti sudah diunggah lebih dari {PROOF_REMIND_HOURS} jam. "
                   "Cek mutasi, lalu konfirmasi pembayaran atau batalkan.",
                   f"order-{order['code']}-ingat-bukti")


def sweep_expired_orders(db, force=False):
    # Dijalankan malas saat ada request, karena serverless tidak punya proses latar belakang
    global _last_sweep
    now_ts = time.monotonic()
    if not force and _last_sweep is not None and now_ts - _last_sweep < EXPIRE_SWEEP_SECONDS:
        return 0
    _last_sweep = now_ts

    cancelled = 0
    try:
        now = utcnow()
        cutoff = now - timedelta(hours=PENDING_TTL_HOURS)
        # Batas bayar tiap pesanan ada di expires_at; created_at hanya cadangan untuk data lama
        stale = list(db.orders.find({"status": "pending", "proof_at": None,   # ada bukti transfer: tidak dibatalkan otomatis
                                     "$or": [{"expires_at": {"$lte": now}},
                                             {"expires_at": {"$exists": False}, "created_at": {"$lt": cutoff}}]}
                                    ).limit(EXPIRE_BATCH))
        for order in stale:
            if cancel_expired_order(db, order):
                cancelled += 1
        remind_cod_orders(db, now)
        remind_proof_orders(db, now)
    except PyMongoError as exc:
        app.logger.error("Penyapuan pesanan kedaluwarsa gagal: %s", exc)
    return cancelled


def cancel_pending_orders(db, user_id, reason):
    cancelled = 0
    for order in db.orders.find({"user_id": user_id, "status": "pending"}):
        changes = {"status": "cancelled", "cancel_reason": reason, "updated_at": utcnow()}
        has_proof = bool(order.get("proof_at"))
        if has_proof:
            changes["payment_issue"] = "proof_cancelled"   # bukti sudah dikirim: uangnya mungkin sudah masuk
        result = db.orders.update_one({"_id": order["_id"], "status": "pending"}, {"$set": changes})
        if result.modified_count != 1:
            continue
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
        cancelled += 1
        if has_proof:
            push_staff("Cek bukti transfer", f"{order['code']} dibatalkan karena akun pelanggan diubah, tetapi bukti transfer sudah diunggah. Cek mutasi.",
                       f"order-{order['code']}-masalah")
    return cancelled


def reserve_stock(db, wanted, expected_prices=None):
    # Stok dikurangi atomik dan hanya berhasil bila cukup, jadi tidak bisa terjual melebihi stok
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
    def __init__(self, order):
        super().__init__("order replay")
        self.order = order


def idempotency_key():
    # Kunci yang sama saat request diulang mencegah pesanan ganda bila jaringan putus
    raw = request.headers.get("Idempotency-Key", "").strip()
    if not raw:
        return None
    if not IDEMPOTENCY_KEY_RE.fullmatch(raw):
        raise ApiError("Permintaan tidak valid. Muat ulang halaman lalu coba lagi.", 422)
    return raw


def replayed_order(db, user, key, wanted):
    if key is None:
        return None
    order = db.orders.find_one({"user_id": user["_id"], "idem_key": key})
    if order is None:
        return None
    if {item["product_id"]: item["qty"] for item in order["items"]} != wanted:
        raise ApiError("Isi keranjang berubah saat pesanan dikirim. Muat ulang halaman lalu coba lagi.", 422)
    return order


def insert_order(db, order, user, key):
    for _ in range(ORDER_CODE_ATTEMPTS):
        order["code"] = new_order_code()
        try:
            db.orders.insert_one(order)
            return order
        except DuplicateKeyError:
            order.pop("_id", None)
            if key is not None:
                existing = db.orders.find_one({"user_id": user["_id"], "idem_key": key})
                if existing:
                    raise OrderReplay(existing)
    raise ApiError("Gagal membuat kode pesanan. Coba lagi.", 503)


def staff_next_statuses(order):
    # COD: uang baru diterima saat barang sampai, jadi tidak lewat "paid" dan boleh dibatalkan saat dikirim
    if order.get("cod"):
        if order["status"] == "pending":
            return {"shipped", "cancelled"}
        if order["status"] == "shipped":
            return {"completed", "cancelled"}
    allowed = set(TRANSITIONS[order["status"]])
    # QRIS dan e-wallet dilunasi oleh Xendit (webhook); staf tidak boleh menandainya dibayar. Hanya transfer bank yang dikonfirmasi manual
    if order["status"] == "pending" and (order.get("payment_method") == "qris" or order.get("payment_method") in EWALLET_CHANNELS):
        allowed.discard("paid")
    return allowed


def check_status_change(user, order, new_status):
    current_status = order["status"]
    if user["role"] == "user":
        # COD: hanya toko yang boleh menyelesaikan, karena penerimaan uang tunai dikonfirmasi toko
        cod_done = order.get("cod") and (current_status, new_status) == ("shipped", "completed")
        if (current_status, new_status) not in USER_TRANSITIONS or cod_done:
            raise ApiError("Anda tidak dapat mengubah pesanan ke status tersebut", 403)
        # Seperti di kebanyakan toko: setelah bukti transfer dikirim, uangnya mungkin sudah masuk, jadi toko yang memutuskan
        if new_status == "cancelled" and order.get("proof_at"):
            raise ApiError("Bukti transfer sudah dikirim, jadi pesanan tidak bisa dibatalkan sendiri. Hubungi toko bila ingin membatalkan.", 409)
    elif new_status not in staff_next_statuses(order):
        raise ApiError(f"Status tidak bisa berubah dari '{current_status}' ke '{new_status}'", 422)


def shipping_fee_for(subtotal, method):
    if method == "pickup" or not SHIPPING_FEE:
        return 0
    if FREE_SHIPPING_MIN and subtotal >= FREE_SHIPPING_MIN:
        return 0
    return SHIPPING_FEE


def pending_filter(user_id, cod):
    # Pesanan tunai menunggu toko, yang lain menunggu pembayaran pelanggan: dua batas terpisah
    return {"user_id": user_id, "status": "pending", "cod": True if cod else {"$ne": True}}


def pending_limit(cod):
    return MAX_PENDING_COD if cod else MAX_PENDING_ORDERS


def enforce_pending_limit(db, user, cod=False):
    # Stok ditahan sejak pesanan dibuat, jadi pesanan yang belum selesai dibatasi per pelanggan
    pending = db.orders.count_documents(pending_filter(user["_id"], cod))
    if pending >= pending_limit(cod):
        raise pending_limit_error(pending, cod)


def pending_limit_error(pending, cod=False):
    if cod:
        return ApiError(
            f"Anda masih punya {pending} pesanan tunai yang menunggu diproses toko. "
            "Tunggu sampai diproses, atau batalkan salah satunya di menu Pesanan sebelum membuat yang baru.",
            429,
        )
    return ApiError(
        f"Anda masih punya {pending} pesanan yang belum dibayar. "
        "Bayar atau batalkan salah satunya di menu Pesanan sebelum membuat yang baru.",
        429,
    )


class GatewayError(Exception):
    pass


def xendit_request(method, path, body=None, timeout=5, version=XENDIT_API_VERSION):
    # Pakai urllib bawaan Python supaya tidak menambah dependensi. Key tidak pernah ditulis ke log.
    token = base64.b64encode(f"{XENDIT_SECRET_KEY}:".encode()).decode()
    headers = {"Authorization": "Basic " + token, "Content-Type": "application/json"}
    if version:
        headers["api-version"] = version
    request_ = urllib.request.Request(
        XENDIT_API_URL + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers)
    try:
        with urllib.request.urlopen(request_, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        app.logger.error("Xendit %s %s -> HTTP %s %s", method, path, exc.code, detail)
        raise GatewayError(f"HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        app.logger.error("Xendit %s %s gagal: %s", method, path, exc)
        raise GatewayError(str(exc)) from exc


def create_xendit_qr(order):
    # reference_id = kode pesanan (unik); nominal dan batas waktu diambil dari pesanan di server
    result = xendit_request("POST", "/qr_codes", {
        "reference_id": order["code"], "type": "DYNAMIC", "currency": "IDR", "amount": order["total"],
        "expires_at": order["expires_at"].replace(microsecond=0).isoformat() + "Z"})
    qr_id, qr_string = result.get("id"), result.get("qr_string")
    if not qr_id or not qr_string:
        raise GatewayError("respons Xendit tidak lengkap")
    return qr_id, qr_string


def create_xendit_ewallet(order, method):
    # API e-wallet Xendit terpisah dari API QR: tanpa header api-version. reference_id = kode pesanan.
    channel = EWALLET_CHANNELS[method]
    # Xendit menuntut https; di balik proxy Vercel host_url bisa terbaca http, jadi dipaksa https bila di Vercel
    base = PUBLIC_URL or request.host_url.rstrip("/")
    if IS_VERCEL and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    props = {"success_redirect_url": f"{base}/?bayar=ok", "failure_redirect_url": f"{base}/?bayar=gagal"}
    if channel == "ID_OVO":
        # OVO tidak memakai tautan: Xendit mengirim notifikasi ke aplikasi OVO sesuai nomor HP
        digits = re.sub(r"\D", "", order["phone"])
        props = {"mobile_number": "+62" + digits.lstrip("0").removeprefix("62")}
    result = xendit_request("POST", "/ewallets/charges", {
        "reference_id": order["code"], "currency": "IDR", "amount": order["total"],
        "checkout_method": "ONE_TIME_PAYMENT", "channel_code": channel, "channel_properties": props},
        version=None)
    charge_id = result.get("id")
    actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
    # DANA memberi tautan web; ShopeePay hanya memberi tautan aplikasi (deeplink); OVO tidak memberi tautan sama sekali
    url = (actions.get("mobile_web_checkout_url") or actions.get("desktop_web_checkout_url")
           or actions.get("mobile_deeplink_checkout_url") or "")
    if not charge_id or (channel != "ID_OVO" and not url):
        given = ",".join(key for key, value in actions.items() if value) or "kosong"
        raise GatewayError(f"respons Xendit tidak lengkap ({channel}, id {'ada' if charge_id else 'tidak ada'}, tautan: {given})")
    return charge_id, url


def drop_unpayable_order(db, order, reason=""):
    # Pesanan dihapus (bukan dibatalkan) supaya percobaan ulang dengan Idempotency-Key yang sama tidak mengembalikan pesanan mati
    if db.orders.delete_one({"_id": order["_id"], "status": "pending"}).deleted_count:
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
        db.order_proofs.delete_one({"_id": order["_id"]})   # foto bukti tidak ditinggalkan tanpa pesanan
        # Alasan dari Xendit (tanpa kunci rahasia) ikut dicatat supaya admin bisa melihatnya di halaman Log
        audit("pesanan_gagal_gateway", f"{order['code']} {reason}".strip()[:240], {"username": "sistem", "role": "-"})


@app.get("/api/orders")
@login_required
def orders_list():
    db = get_db()
    sweep_expired_orders(db)
    user = current_user()
    if user["role"] in STAFF_ROLES:
        # Pesanan berjalan selalu tampil; batas jumlah hanya untuk yang sudah selesai atau batal
        open_orders = db.orders.find({"status": {"$in": list(OPEN_STATUS)}}).sort("created_at", -1).limit(OPEN_ORDERS_LIMIT)
        closed_orders = db.orders.find({"status": {"$nin": list(OPEN_STATUS)}}).sort("created_at", -1).limit(ORDERS_LIMIT)
        docs = sorted([*open_orders, *closed_orders], key=lambda o: o["created_at"], reverse=True)
    else:
        # Pesanan yang sudah dihapus pelanggan hanya disembunyikan; toko tetap menyimpannya untuk laporan
        docs = db.orders.find({"user_id": user["_id"], "hidden_by_user": {"$ne": True}}).sort("created_at", -1).limit(ORDERS_LIMIT)
    return jsonify({"orders": [order_json(settle_overdue(db, o), user) for o in docs]})


@app.post("/api/orders")
@roles_required("user")
def orders_create():
    data = json_body()
    data["phone"] = re.sub(r"[\s.\-]", "", data["phone"]) if isinstance(data.get("phone"), str) else data.get("phone")
    data.setdefault("shipping_method", "delivery")
    data.setdefault("payment_method", PAYMENT_METHODS[0])
    form = Form(data)
    form.choice("shipping_method", "Pengiriman", SHIPPING_METHODS)
    form.choice("payment_method", "Metode pembayaran", PAYMENT_METHODS)
    form.text("phone", "Nomor HP", 8, 16, regex=PHONE_RE, regex_msg=PHONE_ERROR)
    form.text("address", "Alamat pengiriman", 5, 200, required=data["shipping_method"] != "pickup", multiline=True)
    form.text("recipient", "Nama penerima", 2, 50, required=False, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.text("note", "Catatan", 0, 200, required=False, multiline=True)
    clean = form.done()
    if clean["shipping_method"] == "pickup":
        clean["address"] = ""
    wanted = parse_cart_items(data.get("items"))
    expected_prices = parse_expected_prices(data["items"])
    key = idempotency_key()

    db = get_db()
    user = current_user()
    previous = replayed_order(db, user, key, wanted)
    if previous:
        return jsonify({"order": order_json(previous, user), "replayed": True}), 200
    sweep_expired_orders(db)
    enforce_pending_limit(db, user, clean["payment_method"] == "cash")
    reserved, lines = reserve_stock(db, wanted, expected_prices)
    try:
        now = utcnow()
        subtotal = sum(line["subtotal"] for line in lines)
        # Ongkir dan total dihitung di server, angka dari klien tidak dipakai
        fee = shipping_fee_for(subtotal, clean["shipping_method"])
        order = {"user_id": user["_id"], "username": user["username"],
                 "items": lines, "subtotal": subtotal, "shipping_method": clean["shipping_method"],
                 "shipping_fee": fee, "payment_method": clean["payment_method"], "total": subtotal + fee,
                 "phone": clean["phone"], "address": clean["address"], "note": clean["note"],
                 "recipient": clean["recipient"],
                 "cod": clean["payment_method"] == "cash",
                 "status": "pending", "created_at": now, "updated_at": now}
        if clean["payment_method"] == "qris":
            order["expires_at"] = now + timedelta(minutes=QRIS_TTL_MINUTES)
        elif clean["payment_method"] in EWALLET_CHANNELS:
            order["expires_at"] = now + timedelta(minutes=EWALLET_TTL_MINUTES[clean["payment_method"]])
        elif order["cod"]:
            # tunai menunggu toko, bukan pelanggan, jadi batasnya lebih longgar; tanpa batas, pesanan yang ditinggalkan menahan stok selamanya
            order["expires_at"] = now + timedelta(hours=COD_TTL_HOURS)
        else:
            order["expires_at"] = now + timedelta(hours=PENDING_TTL_HOURS)
        if key:
            order["idem_key"] = key
        if clean["payment_method"] == "qris":
            order["pay_token"] = secrets.token_urlsafe(16)
        insert_order(db, order, user, key)
    except OrderReplay as replay:
        release_stock(db, reserved)
        return jsonify({"order": order_json(replay.order, user), "replayed": True}), 200
    except Exception:
        release_stock(db, reserved)
        raise
    # Dua permintaan bersamaan bisa sama-sama lolos pemeriksaan di atas: hitung ulang setelah tersimpan dan batalkan yang berlebih
    pending_now = db.orders.count_documents(pending_filter(user["_id"], order["cod"]))
    if pending_now > pending_limit(order["cod"]):
        drop_unpayable_order(db, order, "melebihi batas pesanan belum dibayar")
        raise pending_limit_error(pending_now - 1, order["cod"])
    if clean["payment_method"] == "qris" and XENDIT_ENABLED:
        try:
            qr_id, qr_string = create_xendit_qr(order)
        except GatewayError as exc:
            drop_unpayable_order(db, order, str(exc))
            raise ApiError("QRIS sedang tidak bisa dibuat. Coba lagi sebentar lagi atau pilih metode lain.", 502)
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"qr_id": qr_id, "qr_string": qr_string}})
        order.update(qr_id=qr_id, qr_string=qr_string)
    if clean["payment_method"] in EWALLET_CHANNELS:
        try:
            charge_id, charge_url = create_xendit_ewallet(order, clean["payment_method"])
        except GatewayError as exc:
            drop_unpayable_order(db, order, str(exc))
            raise ApiError("E-wallet sedang tidak bisa dibuat. Coba lagi sebentar lagi atau pilih metode lain.", 502)
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"ewallet_id": charge_id, "ewallet_url": charge_url}})
        order.update(ewallet_id=charge_id, ewallet_url=charge_url)
    audit("pesanan_buat", f"{order['code']} total {order['total']}")
    push_staff("Pesanan baru", f"{order['code']} · {format_rupiah(order['total'])} · "
                               f"{PAYMENT_NAME.get(order['payment_method'], 'Pesanan')}", f"order-{order['code']}-baru")
    return jsonify({"order": order_json(order, user)}), 201


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
    check_status_change(user, order, new_status)
    now = utcnow()
    changes = {"status": new_status, "updated_at": now}
    # Uang non-COD sudah masuk bila pesanan dibatalkan dari paid/shipped (termasuk retur setelah dikirim): tandai agar dikembalikan
    refund = new_status == "cancelled" and current_status in ("paid", "shipped") and not order.get("cod")
    if refund:
        changes["needs_refund"] = True
    if new_status == "paid":
        changes["paid_at"] = now
    elif new_status == "completed" and order.get("cod") and current_status == "shipped":
        # COD: uang tunai diterima saat pesanan selesai
        changes.update(paid_at=now, paid_via="cash")
    # Status dicek ulang di filter supaya tidak bentrok dengan perubahan lain
    result = db.orders.update_one({"_id": target_id, "status": current_status}, {"$set": changes})
    if result.modified_count != 1:
        raise ApiError("Status pesanan sudah berubah. Muat ulang data.", 409)
    if new_status == "cancelled":
        release_stock(db, [(item["product_id"], item["qty"]) for item in order["items"]])
    audit("pesanan_status", f"{order['code']}: {current_status} → {new_status}" + (" (perlu refund)" if refund else ""))
    if refund:
        push_staff("Perlu refund", f"{order['code']} dibatalkan setelah dibayar. Kembalikan uang pelanggan.",
                   f"order-{order['code']}-refund")
    if user["role"] == "user" and new_status == "cancelled":
        push_staff("Pesanan dibatalkan pelanggan", f"{order['code']} · {format_rupiah(order['total'])} dibatalkan oleh pelanggan.",
                   f"order-{order['code']}-batal")
    # Pelanggan dikabari hanya bila yang mengubah status adalah staf toko (bukan dirinya sendiri)
    if user["role"] != "user" and new_status in CUSTOMER_PUSH:
        title, body = customer_push(new_status, order, refund)
        push_user(order["user_id"], title, body, f"my-{order['code']}-{new_status}")
    return jsonify({"order": order_json(db.orders.find_one({"_id": target_id}), user)})


@app.post("/api/orders/<order_id>/cancel-request")
@roles_required("user")
def order_cancel_request(order_id):
    # Setelah bukti transfer dikirim, uangnya mungkin sudah masuk, jadi pelanggan tidak membatalkan sendiri: ia meminta, staf memutuskan
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"]:
        raise ApiError("Pesanan tidak ditemukan", 404)
    if order["status"] != "pending" or not order.get("proof_at"):
        raise ApiError("Permintaan batal hanya untuk pesanan yang bukti transfernya sudah dikirim dan belum dikonfirmasi. "
                       "Pesanan lain bisa dibatalkan langsung.", 409)
    now = utcnow()
    result = db.orders.update_one(
        {"_id": order["_id"], "status": "pending", "cancel_requested_at": {"$exists": False}},
        {"$set": {"cancel_requested_at": now, "updated_at": now}})
    if result.modified_count == 1:   # permintaan ulang tidak membunyikan notifikasi lagi
        audit("pesanan_minta_batal", order["code"])
        push_staff("Pelanggan minta batal",
                   f"{order['code']} · {format_rupiah(order['total'])}. Bukti transfer sudah diunggah: cek mutasi, lalu batalkan bila setuju.",
                   f"order-{order['code']}-minta-batal")
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


PAY_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
QRIS_ACTOR = {"username": "qris", "role": "-"}


def mark_order_paid(db, order, via, actor=None):
    # Atomik: hanya pesanan yang masih pending yang bisa ditandai dibayar
    now = utcnow()
    result = db.orders.update_one(
        {"_id": order["_id"], "status": "pending"},
        {"$set": {"status": "paid", "paid_at": now, "paid_via": via, "updated_at": now}})
    if result.modified_count != 1:
        return False
    audit("pesanan_status", f"{order['code']}: pending → paid", actor)
    push_staff("Pembayaran masuk", f"{order['code']} · {format_rupiah(order['total'])} sudah dibayar. Siap diproses.",
               f"order-{order['code']}-bayar")
    title, body = CUSTOMER_PUSH["paid"](order["code"])
    push_user(order["user_id"], title, body, f"my-{order['code']}-paid")
    return True


def qris_page(ok, title, lines, status=200):
    color = "#07674c" if ok else "#b42318"
    shape = '<path d="M15 27l8 8 14-19"/>' if ok else '<path d="M18 18l16 16M34 18L18 34"/>'
    icon = (f'<svg viewBox="0 0 52 52" width="84" height="84" fill="none" stroke="{color}" stroke-width="3" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="26" cy="26" r="24"/>{shape}</svg>')
    body = "".join(f"<p>{html_escape(line)}</p>" for line in lines)
    page = ('<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html_escape(title)} - TokoBiru</title>'
            '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f7fc;color:#0c2342;'
            'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;padding:24px;box-sizing:border-box}'
            'main{background:#fff;border:1px solid #dce6f3;border-radius:20px;padding:32px 28px;max-width:360px;width:100%}'
            'h1{font-size:1.35rem;margin:14px 0 8px}p{margin:6px 0;color:#425d7a;line-height:1.45}'
            'small{display:block;margin-top:18px;color:#566f89;font-size:.8rem}</style></head>'
            f'<body><main>{icon}<h1>{html_escape(title)}</h1>{body}'
            '</main></body></html>')
    return Response(page, status=status, mimetype="text/html")


@app.get("/pay/<token>")
def qris_scan(token):
    # Tanpa login: token acak di tautan inilah yang membuktikan pemilik pesanan
    missing = lambda: qris_page(False, "Tautan tidak ditemukan", ["Kode QR ini tidak berlaku."], 404)
    if not (DUMMY_QRIS or XENDIT_SIMULATE_SCAN) or not PAY_TOKEN_RE.fullmatch(token):
        return missing()
    db = get_db()
    order = db.orders.find_one({"pay_token": token})
    if not order:
        return missing()
    order = settle_overdue(db, order)
    if order["status"] == "cancelled":
        return qris_page(False, "Pesanan dibatalkan",
                         [f"Pesanan {order['code']} sudah dibatalkan atau kedaluwarsa.", "Silakan buat pesanan baru."], 410)
    if order["status"] == "pending":
        if XENDIT_SIMULATE_SCAN and order.get("qr_id"):
            try:
                xendit_request("POST", f"/qr_codes/{order['qr_id']}/payments/simulate",
                               {"amount": order["total"]})
            except GatewayError:
                return qris_page(False, "Simulasi gagal", ["Xendit tidak merespons. Coba scan lagi."], 502)
        mark_order_paid(db, order, "xendit" if XENDIT_SIMULATE_SCAN else "qris", QRIS_ACTOR)
    return qris_page(True, "Pembayaran berhasil", [format_rupiah(order["total"]), f"Pesanan {order['code']}"])


@app.post("/api/orders/<order_id>/proof")
@roles_required("user")
def order_proof_upload(order_id):
    # Bukti transfer disimpan di koleksi terpisah (kunci = id pesanan) supaya daftar pesanan tidak ikut memuat gambar
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"] or order.get("payment_method") != "transfer":
        raise ApiError("Pesanan tidak ditemukan", 404)
    order = settle_overdue(db, order)
    if order["status"] != "pending":
        raise ApiError("Bukti hanya bisa diunggah selama pesanan belum dibayar", 409)
    if _hit(f"rl:proofup:{user['_id']}", 3600) > PROOF_UPLOADS_PER_HOUR:
        raise ApiError("Terlalu banyak unggahan bukti dalam satu jam. Coba lagi nanti.", 429)
    form = Form(json_body())
    form.image("image", "Bukti transfer", PROOF_IMAGE_MAX_CHARS)
    clean = form.done()
    if not clean.get("image"):
        raise ApiError("Periksa kembali isian Anda", 422, {"image": "Pilih foto bukti transfer"})
    data, mime = clean["image"]
    now = utcnow()
    # Berapa kali foto bukti pesanan ini diunggah/diganti: mengulang sampai AI "setuju" adalah tanda mencurigakan
    previous = db.order_proofs.find_one({"_id": order["_id"]}, {"revision": 1})
    revision = (previous.get("revision") or 1) + 1 if previous else 1
    db.order_proofs.replace_one({"_id": order["_id"]},
                                {"_id": order["_id"], "image": data, "type": mime, "uploaded_at": now,
                                 "sha256": hashlib.sha256(bytes(data)).hexdigest(), "revision": revision}, upsert=True)
    # Foto baru: hasil baca foto lama tidak berlaku lagi
    db.orders.update_one({"_id": order["_id"], "status": "pending"},
                         {"$set": {"proof_at": now, "updated_at": now}, "$unset": {"proof_check": "", "proof_remind_sent": ""}})
    order = db.orders.find_one({"_id": order["_id"]})   # ambil ulang: Mongo menyimpan waktu dengan ketelitian milidetik
    audit("bukti_transfer", order["code"])

    # Baca otomatis saat unggah. Kegagalan AI tidak boleh menggagalkan unggahan: staf masih punya tombol manual.
    verdict_note = ""
    if PROOF_READER_ENABLED and order.get("proof_at") and proof_read_quota(user, PROOF_AUTO_READS_PER_HOUR):
        try:
            result = analyze_proof(db, order, {"image": data, "type": mime, "revision": revision}, SYSTEM_ACTOR,
                                    timeout=PROOF_UPLOAD_TIMEOUT)
            verdict_note = f" · {PROOF_VERDICT_TEXT.get(result['verdict'], 'Perlu dicek')} ({result['confidence']}%)"
        except Exception as exc:
            app.logger.warning("Baca otomatis saat unggah gagal (%s): %s", order["code"], str(exc)[:200])

    push_staff("Bukti transfer masuk",
               f"{order['code']} · {format_rupiah(order['total'])}{verdict_note}. Cocokkan dengan mutasi, lalu tandai dibayar.",
               f"order-{order['code']}-bukti")
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


@app.get("/api/orders/<order_id>/proof")
@login_required
def order_proof_view(order_id):
    # Hanya pemilik pesanan dan admin
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or (user["role"] == "user" and order["user_id"] != user["_id"]):
        raise ApiError("Bukti tidak ditemukan", 404)
    proof = db.order_proofs.find_one({"_id": order["_id"]})
    if not proof:
        raise ApiError("Bukti tidak ditemukan", 404)
    resp = Response(bytes(proof["image"]), mimetype=proof.get("type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Content-Disposition"] = "inline"
    return resp


def proof_is_reused(db, order_id, digest, reference, fingerprint=None):
    # Foto yang sama persis, nomor referensi transfer yang sama, atau (bila referensi tak terbaca) nominal+menit yang sama
    # sudah dipakai di pesanan lain. Sidik jari nominal+menit menangkap struk yang sama dengan byte berbeda (disimpan ulang,
    # dipotong, tangkapan layar dari tangkapan layar) yang lolos dari pemeriksaan sha256.
    if db.order_proofs.find_one({"sha256": digest, "_id": {"$ne": order_id}}, {"_id": 1}):
        return True
    if reference and len(reference) >= 6:
        return bool(db.orders.find_one({"proof_check.reference": reference, "_id": {"$ne": order_id}}, {"_id": 1}))
    if fingerprint:
        return bool(db.orders.find_one({"proof_check.fingerprint": fingerprint, "_id": {"$ne": order_id}}, {"_id": 1}))
    return False


def read_proof_model(image, mime, model, timeout, thinking):
    """Satu pembacaan oleh satu model. Sebagian model (mis. varian lite) menolak tingkat berpikir "medium" dengan HTTP 400:
    bukan alasan menggagalkan pembacaan, jadi diulang sekali dengan "low" dalam sisa waktu yang sama."""
    started = time.monotonic()
    try:
        return read_transfer_proof(image, mime, GEMINI_API_KEY, model, timeout=timeout, thinking=thinking)
    except ProofReadError as exc:
        left = timeout - (time.monotonic() - started)
        if exc.status == 400 and thinking != "low" and left >= 2:
            app.logger.warning("Model %s menolak thinking=%s (400), diulang dengan low", model, thinking)
            return read_transfer_proof(image, mime, GEMINI_API_KEY, model, timeout=left, thinking="low")
        raise


def read_with_fallback(image, mime, timeout, thinking):
    """Baca dengan model utama; bila server AI sibuk (503/429/5xx) atau kena batas waktu coba model cadangan dalam sisa waktu yang sama.
    Mengembalikan (hasil_baca, nama_model_yang_dipakai). Galat selain itu (kunci salah, foto ditolak, dll.) tidak dicoba ulang."""
    started = time.monotonic()
    models = [PROOF_READER_MODEL]
    if PROOF_READER_FALLBACK_MODEL and PROOF_READER_FALLBACK_MODEL != PROOF_READER_MODEL:
        models.append(PROOF_READER_FALLBACK_MODEL)
    last = None
    # Model utama tidak boleh menghabiskan seluruh waktu: bila ada cadangan dan waktunya longgar (baca manual staf),
    # sisakan sepertiganya supaya batas waktu pada model utama tetap bisa diselamatkan model cadangan
    primary_timeout = timeout * 0.65 if len(models) > 1 and timeout >= 12 else timeout
    for index, model in enumerate(models):
        left = timeout - (time.monotonic() - started)
        if index and left < 2:
            break
        attempt_started = time.monotonic()
        try:
            reading = read_proof_model(image, mime, model, left if index else primary_timeout, thinking)
            took = time.monotonic() - attempt_started
            if took > 5:   # petunjuk untuk menyetel batas waktu dan model: pembacaan selambat ini patut dicatat
                app.logger.warning("Model %s butuh %.1f dtk untuk membaca bukti (thinking=%s)", model, took, thinking)
            return reading, model
        except ProofReadError as exc:
            last = exc
            if not exc.retryable:
                break
            app.logger.warning("Model %s sibuk (%s)%s", model, exc,
                               ", mencoba model cadangan" if index + 1 < len(models) else "")
    raise last


def confirm_reading(image, mime, first_model, started, timeout, thinking):
    """Bacaan kedua atas foto yang sama, oleh model LAIN bila ada (bila tidak, model yang sama), untuk dibandingkan dengan
    bacaan pertama. Mengembalikan None bila waktu tidak cukup atau gagal: hasil tetap dipakai, hanya ditandai belum terkonfirmasi."""
    other = [m for m in (PROOF_READER_MODEL, PROOF_READER_FALLBACK_MODEL) if m and m != first_model]
    model = other[0] if other else first_model
    left = timeout - (time.monotonic() - started)
    if left < PROOF_CONFIRM_MIN_SECONDS:
        return None
    try:
        return read_proof_model(image, mime, model, left, thinking)
    except ProofReadError as exc:
        app.logger.warning("Bacaan kedua (%s) gagal: %s", model, str(exc)[:200])
        return None


def analyze_proof(db, order, proof, actor, timeout=8, deep=False):
    """Baca foto bukti lewat AI, nilai dengan aturan biasa, simpan hasilnya di pesanan, lalu kembalikan.
    Dipakai oleh unggahan pelanggan (otomatis, cepat) dan tombol staf (manual, deep=True: berpikir lebih teliti).
    Hasil yang menentukan (cocok / tidak cocok / mencurigakan) dibaca dua kali oleh model berbeda; bila keduanya tidak sama,
    hasilnya diturunkan menjadi "Perlu dicek". Melempar ProofReadError bila AI gagal."""
    image = bytes(proof["image"])
    mime = proof.get("type") or "image/jpeg"
    thinking = "medium" if deep else "low"
    started = time.monotonic()
    reading, model_used = read_with_fallback(image, mime, timeout, thinking)
    digest = hashlib.sha256(image).hexdigest()
    now = utcnow()
    fingerprint = proof_fingerprint(reading)
    duplicate = proof_is_reused(db, order["_id"], digest, reading["reference"],
                                fingerprint if not reading["reference"] else None)
    rules = dict(total=order["total"], created_at=order["created_at"], now=now, bank_hint=PROOF_BANK_HINT,
                 duplicate=duplicate, uploaded_at=order["proof_at"], revision=proof.get("revision") or 1)
    result = evaluate_proof(reading, **rules)
    if PROOF_CONFIRM_READ and result["verdict"] != "unclear":
        second = confirm_reading(image, mime, model_used, started, timeout, thinking)
        if second is not None:
            result = evaluate_proof(reading, second=second, **rules)
    if not PROOF_CONFIRM_READ:
        result["confirmed"] = None   # bacaan kedua dimatikan: bukan "gagal dikonfirmasi", jadi tidak ada tombol verifikasi ulang
    result.update(proof_at=order["proof_at"], read_at=now, model=model_used)
    db.order_proofs.update_one({"_id": order["_id"]}, {"$set": {"sha256": digest}})   # melengkapi bukti lama
    db.orders.update_one({"_id": order["_id"], "proof_at": order["proof_at"]}, {"$set": {"proof_check": result}})
    unconfirmed = result["confirmed"] is False and result["verdict"] != "unclear"
    audit("bukti_dibaca", f"{order['code']}: {result['verdict']}" + (" (belum terkonfirmasi)" if unconfirmed else ""), actor)
    return result


@app.post("/api/orders/<order_id>/proof/check")
@roles_required(*STAFF_ROLES)
def order_proof_check(order_id):
    # Cadangan manual: dipakai bila pembacaan saat unggah gagal, atau untuk bukti lama yang diunggah sebelum fitur ada
    if not PROOF_READER_ENABLED:
        raise ApiError("Pembacaan otomatis belum diaktifkan", 503)
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order.get("payment_method") != "transfer":
        raise ApiError("Pesanan tidak ditemukan", 404)
    proof = db.order_proofs.find_one({"_id": order["_id"]})
    if not proof or not order.get("proof_at"):
        raise ApiError("Belum ada bukti transfer untuk dibaca", 404)
    cached = order.get("proof_check")
    body = request.get_json(silent=True)
    # Boleh dicoba lagi: hasil "Perlu dicek", atau hasil yang menentukan tetapi belum terkonfirmasi bacaan kedua
    # (confirmed None = bacaan kedua dimatikan atau hasil lama sebelum fitur ini: bukan alasan untuk membaca ulang)
    retryable = bool(cached) and (cached.get("verdict") == "unclear" or
                                  (PROOF_CONFIRM_READ and cached.get("confirmed") is False))
    retry = isinstance(body, dict) and body.get("force") is True and retryable
    if cached and cached.get("proof_at") == order["proof_at"] and not retry:
        return jsonify({"order": order_json(order, user)})   # foto ini sudah dibaca: tidak memanggil AI lagi
    # Pembacaan ulang (force) tetap dihitung dalam batas baca per jam
    if not proof_read_quota(user, PROOF_STAFF_READS_PER_HOUR):
        raise ApiError("Terlalu banyak pembacaan dalam satu jam. Coba lagi nanti atau cek manual.", 429)
    try:
        analyze_proof(db, order, proof, user, timeout=PROOF_STAFF_TIMEOUT, deep=True)
    except ProofReadError as exc:
        app.logger.error("Baca bukti %s gagal: %s", order["code"], exc)
        if exc.status == 429:
            raise ApiError("Kuota layanan AI sedang habis. Tunggu beberapa menit, atau cek manual.", 502)
        if exc.transient:
            raise ApiError("Layanan AI terlalu lama menjawab. Coba lagi, atau cek manual.", 502)
        if exc.retryable:
            raise ApiError("Layanan AI sedang sibuk. Coba lagi beberapa saat lagi, atau cek manual.", 502)
        raise ApiError("Bukti belum bisa dibaca otomatis. Cek manual.", 502)
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


_last_ewallet_sync = {}


def sync_ewallet_status(db, order):
    # Cadangan bila webhook telat/hilang: tanya langsung ke Xendit, paling sering sekali per 3 detik per pesanan
    if order["status"] != "pending" or not order.get("ewallet_id") or not XENDIT_ENABLED:
        return order
    now_ts = time.monotonic()
    if now_ts - _last_ewallet_sync.get(order["_id"], 0) < 3:
        return order
    if len(_last_ewallet_sync) > 500:
        _last_ewallet_sync.clear()
    _last_ewallet_sync[order["_id"]] = now_ts
    try:
        charge = xendit_request("GET", f"/ewallets/charges/{order['ewallet_id']}", timeout=3, version=None)
    except GatewayError:
        return order
    status = str(charge.get("status", "")).upper()
    amount = charge.get("charge_amount")
    if status in XENDIT_PAID_STATUS and isinstance(amount, (int, float)) and amount == order["total"]:
        mark_order_paid(db, order, "xendit", XENDIT_ACTOR)
    elif status == "FAILED":
        cancel_expired_order(db, order, "payment_failed", "pesanan_bayar_gagal")
    else:
        return order
    return db.orders.find_one({"_id": order["_id"]}) or order


@app.get("/api/orders/<order_id>/status")
@login_required
def order_status_poll(order_id):
    db = get_db()
    sweep_expired_orders(db)
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or (user["role"] == "user" and order["user_id"] != user["_id"]):
        raise ApiError("Pesanan tidak ditemukan", 404)
    order = sync_ewallet_status(db, settle_overdue(db, order))
    return jsonify({"status": order["status"]})


@app.post("/api/orders/<order_id>/simulate-pay")
@roles_required("user")
def order_simulate_pay(order_id):
    if not DUMMY_QRIS:
        raise ApiError("QRIS tidak aktif", 404)
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"] or order.get("payment_method") != "qris":
        raise ApiError("Pesanan tidak ditemukan", 404)
    order = settle_overdue(db, order)
    if order["status"] == "cancelled":
        raise ApiError("Pesanan sudah dibatalkan atau kedaluwarsa", 409)
    mark_order_paid(db, order, "qris")
    return jsonify({"order": order_json(db.orders.find_one({"_id": order["_id"]}), user)})


XENDIT_PAID_STATUS = ("SUCCEEDED", "COMPLETED")
XENDIT_ACTOR = {"username": "xendit", "role": "-"}


@app.post("/webhooks/xendit")
def xendit_webhook():
    # Di luar /api/ karena dipanggil server Xendit (tanpa sesi dan token CSRF); keasliannya dibuktikan oleh x-callback-token
    if not XENDIT_ENABLED:
        return jsonify({"error": "tidak aktif"}), 404
    sent = request.headers.get("x-callback-token", "")
    if not secrets.compare_digest(sent.encode(), XENDIT_CALLBACK_TOKEN.encode()):
        app.logger.warning("Webhook Xendit ditolak: token salah dari %s", client_ip())
        return jsonify({"error": "token tidak valid"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "format tidak valid"}), 400

    event = payload.get("event")
    data = payload["data"] if isinstance(payload.get("data"), dict) else payload
    is_ewallet = event == "ewallet.capture"
    reference, qr_id = data.get("reference_id"), data.get("qr_id")
    amount = data.get("charge_amount", data.get("amount")) if is_ewallet else data.get("amount")
    status = str(data.get("status", "")).upper()
    paid = status in XENDIT_PAID_STATUS
    # E-wallet ditolak pelanggan atau tagihan kedaluwarsa di sisi e-wallet
    failed = is_ewallet and status == "FAILED"
    # Event lain (mis. refund) dan status selain lunas diabaikan; 200 supaya Xendit tidak mengirim ulang
    if (event and event not in ("qr.payment", "ewallet.capture")) or not (paid or failed) or not isinstance(reference, str):
        # Token sudah terbukti benar di atas, jadi aman dicatat (bukan lalu lintas liar); membantu melacak notifikasi yang tidak melunasi
        audit("webhook_diabaikan", f"{event or '-'} {status or '-'} {str(reference)[:40]}", XENDIT_ACTOR)
        return jsonify({"ok": True, "ignored": True}), 200

    db = get_db()
    if is_ewallet:
        order = db.orders.find_one({"code": reference, "payment_method": {"$in": list(EWALLET_CHANNELS)}})
        # Nomor transaksi e-wallet harus sama dengan yang tersimpan di pesanan
        if order and order.get("ewallet_id") and data.get("id") and data["id"] != order["ewallet_id"]:
            order = None
    else:
        order = db.orders.find_one({"code": reference, "payment_method": "qris"})
    if not order:
        audit("pembayaran_tak_dikenal", reference[:40], XENDIT_ACTOR)
        return jsonify({"ok": True, "ignored": True}), 200

    if failed:
        # Batalkan sekarang supaya stok tidak tertahan sampai batas waktu toko habis; bila sudah tidak pending, tidak ada yang berubah
        cancel_expired_order(db, order, "payment_failed", "pesanan_bayar_gagal")
        return jsonify({"ok": True})

    amount_ok = isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount == order["total"]
    qr_ok = not (order.get("qr_id") and qr_id and qr_id != order["qr_id"])
    if not amount_ok or not qr_ok:
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"payment_issue": "mismatch", "updated_at": utcnow()}})
        audit("pembayaran_tidak_cocok", f"{order['code']} nominal {amount} vs {order['total']}", XENDIT_ACTOR)
        push_staff("Pembayaran tidak cocok", f"{order['code']}: nominal yang masuk berbeda. Perlu dicek.",
                   f"order-{order['code']}-masalah")
        return jsonify({"ok": True, "ignored": True}), 200

    if order["status"] == "pending":
        mark_order_paid(db, order, "xendit", XENDIT_ACTOR)
    elif order["status"] == "cancelled":
        # Uang masuk setelah pesanan dibatalkan/kedaluwarsa: stok sudah dilepas, jadi ditandai untuk refund manual
        db.orders.update_one({"_id": order["_id"]}, {"$set": {"needs_refund": True, "updated_at": utcnow()}})
        audit("pembayaran_terlambat", f"{order['code']} dibayar setelah dibatalkan, perlu refund", XENDIT_ACTOR)
        push_staff("Perlu refund", f"{order['code']} dibayar setelah dibatalkan. Kembalikan uang pelanggan.",
                   f"order-{order['code']}-refund")
    return jsonify({"ok": True})


@app.post("/api/orders/<order_id>/issue-resolved")
@roles_required(*STAFF_ROLES)
def order_issue_resolved(order_id):
    # Admin menandai bahwa refund atau selisih nominal sudah diurus (uangnya sendiri dikembalikan lewat Dashboard Xendit)
    db = get_db()
    user = current_user()
    order = db.orders.find_one_and_update(
        {"_id": object_id(order_id, "Pesanan"), "$or": [{"needs_refund": True}, {"payment_issue": {"$exists": True}}]},
        {"$unset": {"needs_refund": "", "payment_issue": ""}, "$set": {"updated_at": utcnow()}},
        return_document=ReturnDocument.AFTER)
    if not order:
        raise ApiError("Pesanan ini tidak punya masalah pembayaran yang perlu ditangani", 404)
    audit("pembayaran_masalah_selesai", order["code"])
    return jsonify({"order": order_json(order, user)})


@app.delete("/api/orders/<order_id>")
@roles_required("user")
def order_hide(order_id):
    # Hapus lunak: pesanan hilang dari daftar pelanggan, data toko (omzet, log) tidak berubah
    db = get_db()
    user = current_user()
    order = db.orders.find_one({"_id": object_id(order_id, "Pesanan")})
    if not order or order["user_id"] != user["_id"]:
        raise ApiError("Pesanan tidak ditemukan", 404)
    if order["status"] not in CLOSED_STATUS:
        raise ApiError("Hanya pesanan selesai atau dibatalkan yang bisa dihapus", 409)
    db.orders.update_one({"_id": order["_id"]}, {"$set": {"hidden_by_user": True, "hidden_at": utcnow()}})
    audit("pesanan_hapus", order["code"])
    return jsonify({"ok": True})


@app.post("/api/orders/clear-history")
@roles_required("user")
def orders_clear_history():
    db = get_db()
    user = current_user()
    result = db.orders.update_many(
        {"user_id": user["_id"], "status": {"$in": list(CLOSED_STATUS)}, "hidden_by_user": {"$ne": True}},
        {"$set": {"hidden_by_user": True, "hidden_at": utcnow()}})
    if result.modified_count:
        audit("pesanan_bersihkan", f"{result.modified_count} pesanan")
    return jsonify({"removed": result.modified_count})


def order_summary(db):
    by_status = {status: 0 for status in ORDER_STATUS}
    revenue = paid_orders = 0
    pipeline = [{"$group": {"_id": {"status": "$status", "cod": {"$eq": ["$cod", True]}},
                            "n": {"$sum": 1}, "sum": {"$sum": "$total"}}}]
    for row in db.orders.aggregate(pipeline):
        status, cod = row["_id"]["status"], row["_id"].get("cod", False)
        if status in by_status:
            by_status[status] += row["n"]
            # COD yang masih dikirim belum dihitung: uangnya baru diterima saat selesai
            if status in REVENUE_STATUS and not (cod and status == "shipped"):
                revenue += row["sum"]
                paid_orders += row["n"]
    return by_status, revenue, paid_orders


def today_summary(db):
    local_now = utcnow() + WIB_OFFSET
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - WIB_OFFSET
    revenue = 0
    paid_today = {"$or": [{"paid_at": {"$gte": start}},
                          {"paid_at": {"$exists": False}, "created_at": {"$gte": start}}]}
    pipeline = [{"$match": {**paid_today, "status": {"$in": list(REVENUE_STATUS)},
                            "$nor": [{"cod": True, "status": "shipped"}]}},
                {"$group": {"_id": None, "sum": {"$sum": "$total"}}}]
    for row in db.orders.aggregate(pipeline):
        revenue = row["sum"]
    return {"orders": db.orders.count_documents({"created_at": {"$gte": start}}), "revenue": revenue}


@app.get("/api/stats")
@roles_required(*STAFF_ROLES)
def stats():
    db = get_db()
    sweep_expired_orders(db)
    by_status, revenue, paid_orders = order_summary(db)
    low_stock = (db[PRODUCT_COLLECTION].find({"stock": {"$lte": LOW_STOCK_LIMIT}}, NO_IMAGE)
                 .sort("stock", 1).limit(LOW_STOCK_LIST_SIZE))
    recent = db.orders.find().sort("created_at", -1).limit(RECENT_ORDERS_SIZE)
    result = {
        "revenue": revenue,
        "paid_orders": paid_orders,
        "today": today_summary(db),
        "orders": {"total": sum(by_status.values()), **by_status},
        "products": db[PRODUCT_COLLECTION].count_documents({}),
        "low_stock": [product_json(p) for p in low_stock],
        "low_stock_total": db[PRODUCT_COLLECTION].count_documents({"stock": {"$lte": LOW_STOCK_LIMIT}}),
        "out_of_stock_total": db[PRODUCT_COLLECTION].count_documents({"stock": 0}),
        "recent": [serialize(o) for o in recent],
        "users": None,
    }
    if current_user()["role"] == "master":
        result["users"] = {role: db.users.count_documents({"role": role}) for role in ROLES}
    return jsonify(result)


def user_listing(doc):
    out = serialize(doc)
    if doc.get("image_v"):
        out["photo"] = f"/api/users/{out['id']}/avatar?v={int(doc['image_v'])}"
    return out


def forget_user_devices(db, user_id, notifications=False):
    """Lepas perangkat push akun ini; notifikasi dalam aplikasi ikut dihapus bila `notifications` (kabar staf tidak boleh tersisa)."""
    db.push_subs.delete_many({"user_id": user_id})
    if notifications:
        db.notifications.delete_many({"user_id": user_id})


@app.get("/api/users")
@roles_required("master")
def users_list():
    docs = get_db().users.find({}, {"image": 0}).sort("created_at", 1).limit(USERS_LIMIT)
    return jsonify({"users": [user_listing(u) for u in docs]})


@app.get("/api/users/<user_id>/avatar")
@roles_required("master")
def users_avatar(user_id):
    target_id = object_id(user_id, "Pengguna")
    doc = get_db().users.find_one({"_id": target_id}, {"image": 1, "image_type": 1})
    if not doc or not doc.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(doc["image"]), mimetype=doc.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


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
    if target["role"] in STAFF_ROLES and changes.get("role") == "user":
        forget_user_devices(db, target_id, notifications=True)   # bukan staf lagi: kabar tokonya tidak boleh tersisa
    if changes.get("active") is False:
        forget_user_devices(db, target_id)
        freed = cancel_pending_orders(db, target_id, "account_disabled")
        if freed:
            detail += f" ({freed} pesanan belum dibayar dibatalkan)"
    audit("user_ubah", detail)
    return jsonify({"user": user_listing(db.users.find_one({"_id": target_id}, {"image": 0}))})


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


@app.get("/api/logs")
@roles_required("master")
def logs_list():
    docs = get_db().logs.find().sort("ts", -1).limit(LOGS_LIMIT)
    return jsonify({"logs": [serialize(log) for log in docs]})


@app.post("/api/logs/delete")
@roles_required("master")
def logs_delete():
    ids = json_body().get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= LOGS_LIMIT:
        raise ApiError(f"Pilih 1 sampai {LOGS_LIMIT} log", 422)
    oids = list({object_id(item, "Log") for item in ids})
    db = get_db()
    # Ringkasan dicatat sebelum dihapus; isi log yang dihapus tidak disimpan, hanya berapa banyak dan rentang waktunya
    doomed = list(db.logs.find({"_id": {"$in": oids}}, {"ts": 1}))
    result = db.logs.delete_many({"_id": {"$in": oids}})
    if result.deleted_count:
        stamps = sorted(doc["ts"] for doc in doomed if doc.get("ts"))
        span = (f", {(stamps[0] + WIB_OFFSET).strftime('%d/%m/%y %H:%M')} s/d {(stamps[-1] + WIB_OFFSET).strftime('%d/%m/%y %H:%M')} WIB"
                if stamps else "")
        audit("log_hapus", f"{result.deleted_count} log dihapus{span}")
    return jsonify({"deleted": result.deleted_count})


@app.get("/api/health")
def health():
    get_db().command("ping")
    return jsonify({"status": "ok"})


def bootstrap(db):
    username, email = (_env_str(key) for key in ("MASTER_USERNAME", "MASTER_EMAIL"))
    password = _env_str("MASTER_PASSWORD", strip=False)
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


def gen_vapid_cli():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())

    def b64(raw):
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    private = b64(key.private_numbers().private_value.to_bytes(32, "big"))
    public = b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    print("Salin ke Environment Variables (Vercel) atau .env. Jaga kunci privat, jangan dibagikan.\n")
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:emailanda@contoh.com")


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


@app.get("/")
def index():
    return send_from_directory(TEMPLATE_DIR, "index.html", mimetype="text/html")


@app.get("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-master":
        create_master_cli()
    elif len(sys.argv) > 1 and sys.argv[1] == "seed-demo":
        seed_demo_cli()
    elif len(sys.argv) > 1 and sys.argv[1] == "gen-vapid":
        gen_vapid_cli()
    else:
        app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)),
                debug=os.environ.get("FLASK_DEBUG") == "1")