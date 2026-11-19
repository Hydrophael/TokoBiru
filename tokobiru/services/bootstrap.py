from flask import current_app
from pymongo.errors import PyMongoError

from tokobiru.core.config import PRODUCT_COLLECTION, _env_str
from tokobiru.core.util import utcnow
from tokobiru.services.users import new_user_doc


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
        current_app.logger.error("Bootstrap gagal: %s", exc)


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