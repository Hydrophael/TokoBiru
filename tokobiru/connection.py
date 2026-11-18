"""TokoBiru - koneksi MongoDB: alamat, nama database, migrasi koleksi lama, dan indeks.

get_db() menyimpan koneksi di _db. Tes memasang database tiruan dengan mengganti tokobiru.connection._db
(lihat use_db di tests/conftest.py). Nama-nama selain _db masih diimpor ulang oleh app.py.
"""
import logging

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError

from tokobiru.config import (IS_VERCEL, LEGACY_PRODUCT_COLLECTION, LOG_RETENTION_DAYS,
                             PRODUCT_COLLECTION, PROOF_RETENTION_DAYS, _env_str)

log = logging.getLogger("app")   # logger yang sama dengan app.logger

# Diisi app.py (bootstrap): dipanggil sekali setelah koneksi pertama berhasil
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


def ensure_unique_order_code_index(db):
    # Kode pesanan dipakai sebagai referensi bayar, jadi harus unik
    try:
        db.orders.create_index([("code", ASCENDING)], unique=True)
    except OperationFailure as exc:
        log.error("Indeks unik orders.code gagal dibuat (ada kode ganda di data lama?): %s", exc)


def ensure_ttl_index(coll, field, days, name):
    """Indeks TTL (dokumen terhapus otomatis `days` hari setelah `field`). Bila lama simpan diubah lewat .env, indeks lama diperbarui."""
    seconds = days * 86400
    try:
        coll.create_index([(field, ASCENDING)], expireAfterSeconds=seconds, name=name)
    except OperationFailure:
        try:
            coll.database.command("collMod", coll.name, index={"name": name, "expireAfterSeconds": seconds})
        except PyMongoError as exc:
            log.error("Indeks TTL %s gagal diperbarui: %s", name, exc)


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
    if after_connect:
        after_connect(db)
    return db
