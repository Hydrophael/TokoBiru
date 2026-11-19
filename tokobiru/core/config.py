"""TokoBiru - konfigurasi: environment variable dan konstanta aplikasi.

Semua nilai dibaca sekali saat modul diimpor. Modul lain memakainya lewat
`from tokobiru import config` lalu `config.NAMA`, atau (sementara, selama app.py
masih besar) lewat `from tokobiru.core.config import *`.
"""
import os
import re
import secrets
import sys
from datetime import timedelta

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
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # akar proyek (satu tingkat di atas paket ini)
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

SECRET_KEY = _env_str("SECRET_KEY")
if not SECRET_KEY:
    if IS_VERCEL:
        raise RuntimeError("SECRET_KEY belum diset di Environment Variables Vercel.")
    SECRET_KEY = secrets.token_hex(32)

MAX_JSON_BYTES = 64 * 1024
MAX_PRODUCT_BODY_BYTES = 1024 * 1024   # foto bukti transfer lebih besar (lihat PROOF_IMAGE_MAX_CHARS)
PRODUCT_WRITE_RE = re.compile(r"/api/products(?:/[0-9a-fA-F]{24})?")
PROFILE_WRITE_RE = re.compile(r"/api/auth/profile")
PROOF_WRITE_RE = re.compile(r"/api/orders/[0-9a-fA-F]{24}/proof")

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
INDEX_SETUP_ON_CONNECT = _env_str("INDEX_SETUP", "1").lower() not in ("0", "false", "off", "tidak")
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


PRODUCT_COLLECTION = "master_product"
LEGACY_PRODUCT_COLLECTION = "products"


VAPID_PUBLIC_KEY = _env_str("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = _env_str("VAPID_PRIVATE_KEY")
_SUBJECT_OK = re.compile(r"^mailto:[^@\s]+@[^@\s]+\.[^@\s]+$|^https://\S+$", re.I)

def _vapid_subject():
    raw = _env_str("VAPID_SUBJECT")
    if raw and _SUBJECT_OK.match(raw):
        return raw
    sender = SMTP_FROM or SMTP_USER
    if sender and "@" in sender:
        return f"mailto:{sender}"
    return ""

VAPID_SUBJECT = _vapid_subject()
PUSH_MAX_DEVICES_PER_USER = 5
PUSH_MAX_SUBS = 200
PUSH_TIMEOUT = 3
PUSH_BUDGET = 4
PUSH_HOST_SUFFIXES = ("googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")
PUSH_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{8,200}={0,2}")
PAYMENT_NAME = {"transfer": "Transfer", "cash": "Bayar di tempat", "qris": "QRIS",
                "ewallet_dana": "DANA", "ewallet_shopeepay": "ShopeePay", "ewallet_ovo": "OVO"}