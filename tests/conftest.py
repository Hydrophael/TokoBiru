"""Fixture bersama: aplikasi Flask dengan MongoDB tiruan (mongomock) di memori.

Tes tidak menyentuh MongoDB sungguhan, jadi aman dijalankan di mana saja.
"""
import os
import sys

import mongomock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- isolasi tes: harus sebelum "import app" ---
# Tes tidak boleh bergantung pada .env pribadi maupun versi mongomock.
# Nilai di bawah ini yang dianggap benar oleh tes (transfer aktif, tanpa ongkir).
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
os.environ["SHIPPING_FEE"] = "0"
# Pengaman: bila patch _db meleset, koneksi gagal dengan jelas dan tidak menyentuh database asli
os.environ["MONGO_URI"] = "mongodb://127.0.0.1:1"
os.environ["PAY_INFO"] = "BCA 1234567890 a.n. TokoBiru Uji"

from mongomock.collection import BulkOperationBuilder as _Bulk
_add_update = _Bulk.add_update
_Bulk.add_update = lambda self, *a, sort=None, **k: _add_update(self, *a, **k)
# --- akhir isolasi ---
import app as tokobiru  # noqa: E402

PASSWORD = "rahasia123"


@pytest.fixture()
def db(monkeypatch, use_db):
    fake = mongomock.MongoClient()["tokobiru_test"]
    tokobiru.ensure_indexes(fake)
    use_db(fake, reset_sweep=False)
    # hash cepat supaya tes tidak lambat
    monkeypatch.setattr(tokobiru, "generate_password_hash", lambda p: "plain:" + p)
    monkeypatch.setattr(tokobiru, "check_password_hash", lambda h, p: h == "plain:" + p)
    monkeypatch.setattr(tokobiru, "DUMMY_HASH", "plain:tidak-akan-cocok")
    return fake


@pytest.fixture()
def use_db(monkeypatch):
    """Satu-satunya tempat tes memasang database tiruan. Bila _db pindah modul, cukup ubah di sini."""
    def apply(database, reset_sweep=True):
        monkeypatch.setattr(tokobiru, "_db", database)
        if reset_sweep:
            monkeypatch.setattr(tokobiru, "_last_sweep", None)
        return database
    return apply


class Client:
    """Pembungkus test client: mengurus token CSRF dan login."""

    def __init__(self, flask_client):
        self.c = flask_client
        self.csrf = ""
        self.refresh()

    def refresh(self):
        self.csrf = self.c.get("/api/auth/me").get_json()["csrf"]

    def _headers(self):
        return {"X-CSRF-Token": self.csrf}

    def get(self, path):
        return self.c.get(path)

    def post(self, path, body=None):
        return self.c.post(path, json=body if body is not None else {}, headers=self._headers())

    def put(self, path, body):
        return self.c.put(path, json=body, headers=self._headers())

    def patch(self, path, body):
        return self.c.patch(path, json=body, headers=self._headers())

    def delete(self, path):
        return self.c.delete(path, json={}, headers=self._headers())  # frontend selalu kirim Content-Type JSON

    def login(self, identifier, password=PASSWORD):
        resp = self.post("/api/auth/login", {"identifier": identifier, "password": password})
        if resp.status_code == 200:
            self.csrf = resp.get_json()["csrf"]
        return resp


@pytest.fixture()
def make_client(db):
    tokobiru.app.config["TESTING"] = True

    def factory():
        return Client(tokobiru.app.test_client())
    return factory


@pytest.fixture()
def anon(make_client):
    return make_client()


def _login_as(make_client, username):
    client = make_client()
    assert client.login(username).status_code == 200
    return client


def _add_user(db, username, role):
    doc = tokobiru.new_user_doc(
        {"name": username.capitalize(), "username": username,
         "email": f"{username}@contoh.id", "password": PASSWORD}, role)
    db.users.insert_one(doc)
    return doc


@pytest.fixture()
def users(db):
    return {role: _add_user(db, role, role) for role in ("master", "admin", "user")}


@pytest.fixture()
def other_customer(db, make_client):
    """Pelanggan kedua, untuk menguji pemisahan data antar pelanggan."""
    _add_user(db, "siti", "user")
    return _login_as(make_client, "siti")


@pytest.fixture()
def master(make_client, users):
    return _login_as(make_client, "master")


@pytest.fixture()
def admin(make_client, users):
    return _login_as(make_client, "admin")


@pytest.fixture()
def customer(make_client, users):
    return _login_as(make_client, "user")


@pytest.fixture()
def product(db):
    doc = {"name": "Beras 5kg", "category": "Sembako", "price": 65000, "stock": 10,
           "description": "", "created_at": tokobiru.utcnow(), "updated_at": tokobiru.utcnow()}
    db[tokobiru.PRODUCT_COLLECTION].insert_one(doc)
    return doc