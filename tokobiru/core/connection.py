"""TokoBiru - koneksi MongoDB: alamat, nama database, migrasi koleksi lama, dan indeks.

get_db() menyimpan koneksi di _db. Tes memasang database tiruan dengan mengganti tokobiru.core.connection._db
(lihat use_db di tests/conftest.py).

Indeks dibuat saat koneksi pertama tiap instance (cold start) selama INDEX_SETUP tidak diisi 0. Satu indeks yang
gagal karena konflik data atau opsi (OperationFailure) dicatat dan tidak menghentikan indeks lain maupun aplikasi.
Galat jaringan tetap dilempar dan koneksi tidak disimpan, jadi request berikutnya mencoba lagi.
"""
import logging

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError

from tokobiru.core.config import (
    INDEX_SETUP_ON_CONNECT,
    IS_VERCEL,
    LEGACY_PRODUCT_COLLECTION,
    LOG_RETENTION_DAYS,
    PRODUCT_COLLECTION,
    PROOF_RETENTION_DAYS,
    _env_str,
)

log = logging.getLogger("app")   # logger yang sama dengan current_app.logger

# Diisi create_app (bootstrap): dipanggil sekali setelah koneksi pertama berhasil
after_connect = None

_db = None


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


def ensure_ttl_index(coll, field, days, name):
    """Indeks TTL (dokumen terhapus otomatis `days` hari setelah `field`). Bila lama simpan diubah lewat .env, indeks lama diperbarui.
    Mengembalikan True bila indeks siap, False bila gagal (sudah dicatat di log)."""
    seconds = days * 86400
    try:
        coll.create_index([(field, ASCENDING)], expireAfterSeconds=seconds, name=name)
        return True
    except OperationFailure:
        try:
            coll.database.command("collMod", coll.name, index={"name": name, "expireAfterSeconds": seconds})
            return True
        except PyMongoError as exc:
            log.error("Indeks TTL %s gagal diperbarui: %s", name, exc)
            return False


def _create_index(failed, coll, keys, **options):
    """Buat satu indeks. Konflik (data ganda, opsi berbeda) dicatat dan dikumpulkan di `failed`, indeks lain tetap dibuat."""
    try:
        coll.create_index(keys, **options)
    except OperationFailure as exc:
        name = options.get("name") or "_".join(f"{field}_{direction}" for field, direction in keys)
        log.error("Indeks %s.%s gagal dibuat: %s", coll.name, name, exc)
        failed.append(f"{coll.name}.{name}")


def ensure_indexes(db):
    """Buat semua indeks yang dibutuhkan (aman dipanggil berulang). Mengembalikan daftar indeks yang gagal; kosong = semua siap."""
    failed = []

    def index(coll, keys, **options):
        _create_index(failed, coll, keys, **options)

    def ttl(coll, field, days, name):
        if not ensure_ttl_index(coll, field, days, name):
            failed.append(f"{coll.name}.{name}")

    products = db[PRODUCT_COLLECTION]
    index(db.users, [("username", ASCENDING)], unique=True)
    index(db.users, [("email", ASCENDING)], unique=True)
    index(products, [("name", ASCENDING)])
    index(products, [("category", ASCENDING)])
    index(products, [("stock", ASCENDING)])
    index(products, [("name", "text"), ("category", "text"), ("description", "text")],
          weights={"name": 5, "category": 2, "description": 1}, default_language="none", name="product_text")
    index(db.orders, [("user_id", ASCENDING), ("created_at", DESCENDING)])
    index(db.orders, [("status", ASCENDING), ("created_at", ASCENDING)])
    index(db.orders, [("created_at", DESCENDING)])
    index(db.orders, [("paid_at", DESCENDING)])
    index(db.orders, [("user_id", ASCENDING), ("idem_key", ASCENDING)], unique=True,
          partialFilterExpression={"idem_key": {"$type": "string"}})
    # Kode pesanan dipakai sebagai referensi bayar, jadi harus unik (gagal bila ada kode ganda di data lama)
    index(db.orders, [("code", ASCENDING)], unique=True)
    index(db.orders, [("proof_check.reference", ASCENDING)], sparse=True)
    index(db.orders, [("proof_check.fingerprint", ASCENDING)], sparse=True)
    index(db.logs, [("ts", DESCENDING)])
    ttl(db.logs, "ts", LOG_RETENTION_DAYS, "logs_ttl")
    index(db.rate_limits, [("expires", ASCENDING)], expireAfterSeconds=0, name="rate_ttl")
    index(db.push_subs, [("user_id", ASCENDING)])
    index(db.order_proofs, [("sha256", ASCENDING)])
    ttl(db.order_proofs, "uploaded_at", PROOF_RETENTION_DAYS, "proof_ttl")
    index(db.notifications, [("user_id", ASCENDING), ("created_at", DESCENDING)])
    index(db.notifications, [("created_at", ASCENDING)], expireAfterSeconds=30 * 86400, name="notif_ttl")
    return failed


def get_db():
    global _db
    if _db is not None:
        return _db
    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=6000, appname="tokobiru")
    db = client[mongo_db_name()]
    migrate_legacy_collections(db)
    if INDEX_SETUP_ON_CONNECT:
        ensure_indexes(db)
    _db = db
    if after_connect:
        after_connect(db)
    return db