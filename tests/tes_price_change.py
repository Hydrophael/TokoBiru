"""Tes untuk peringatan harga berubah saat checkout (harga yang dilihat pelanggan vs harga di database)."""
import os
import sys

import mongomock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as tb  # noqa: E402


@pytest.fixture
def db(monkeypatch):
    database = mongomock.MongoClient().tokobiru
    monkeypatch.setattr(tb, "_db", database)
    monkeypatch.setattr(tb, "_last_sweep", None)
    return database


def make_user(db, username, role="user"):
    db.users.insert_one(tb.new_user_doc({
        "name": username.title(), "username": username,
        "email": f"{username}@t.test", "password": "rahasia123"}, role))


def login(username):
    client = tb.app.test_client()
    csrf = client.get("/api/auth/me").get_json()["csrf"]
    res = client.post("/api/auth/login", json={"identifier": username, "password": "rahasia123"},
                      headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200, res.get_json()
    client.csrf = res.get_json()["csrf"]
    return client


def add_product(db, name="Teh Celup", stock=10, price=5000):
    now = tb.utcnow()
    return db[tb.PRODUCT_COLLECTION].insert_one({
        "name": name, "category": "Minuman", "price": price, "stock": stock,
        "description": "", "created_at": now, "updated_at": now}).inserted_id


def stock_of(db, pid):
    return db[tb.PRODUCT_COLLECTION].find_one({"_id": pid})["stock"]


def set_price(db, pid, price):
    db[tb.PRODUCT_COLLECTION].update_one({"_id": pid}, {"$set": {"price": price}})


def place(client, lines, key=None):
    """lines: daftar (product_id, qty, harga_yang_dilihat). Harga None berarti klien lama (tanpa harga)."""
    items = []
    for pid, qty, price in lines:
        item = {"product_id": str(pid), "qty": qty}
        if price is not None:
            item["price"] = price
        items.append(item)
    headers = {"X-CSRF-Token": client.csrf}
    if key is not None:
        headers["Idempotency-Key"] = key
    body = {"items": items, "address": "Jl. Melati 5, Solo", "phone": "081234567890"}
    return client.post("/api/orders", json=body, headers=headers)


# --- harga sama / klien lama -----------------------------------------------
def test_harga_sama_diterima(db):
    make_user(db, "budi")
    pid = add_product(db, price=5000)
    res = place(login("budi"), [(pid, 2, 5000)])
    assert res.status_code == 201
    order = res.get_json()["order"]
    assert order["total"] == 10000 and order["items"][0]["price"] == 5000


def test_tanpa_harga_tetap_diterima(db):
    make_user(db, "budi")
    pid = add_product(db, price=5000)
    set_price(db, pid, 6000)                      # klien lama tidak mengirim harga, jadi tidak diperiksa
    res = place(login("budi"), [(pid, 1, None)])
    assert res.status_code == 201
    assert res.get_json()["order"]["total"] == 6000


# --- harga berubah ----------------------------------------------------------
def test_harga_berubah_ditolak(db):
    make_user(db, "budi")
    pid = add_product(db, price=5000, stock=10)
    budi = login("budi")
    set_price(db, pid, 6000)                      # admin menaikkan harga setelah katalog dimuat

    res = place(budi, [(pid, 2, 5000)])
    assert res.status_code == 409
    message = res.get_json()["error"]
    assert "Teh Celup" in message and "Rp5.000" in message and "Rp6.000" in message
    assert db.orders.count_documents({}) == 0
    assert stock_of(db, pid) == 10                # tidak ada stok yang terpotong


def test_setelah_harga_diperbarui_pesanan_diterima(db):
    make_user(db, "budi")
    pid = add_product(db, price=5000)
    budi = login("budi")
    set_price(db, pid, 6000)
    assert place(budi, [(pid, 1, 5000)]).status_code == 409
    res = place(budi, [(pid, 1, 6000)])           # katalog dimuat ulang, harga baru dikirim
    assert res.status_code == 201 and res.get_json()["order"]["total"] == 6000


def test_harga_produk_kedua_berubah_mengembalikan_stok_produk_pertama(db):
    make_user(db, "budi")
    teh = add_product(db, name="Teh Celup", price=5000, stock=10)
    kopi = add_product(db, name="Kopi Bubuk", price=24000, stock=10)
    budi = login("budi")
    set_price(db, kopi, 26000)

    res = place(budi, [(teh, 3, 5000), (kopi, 1, 24000)])
    assert res.status_code == 409 and "Kopi Bubuk" in res.get_json()["error"]
    assert stock_of(db, teh) == 10                # stok teh yang sempat dipotong dikembalikan
    assert stock_of(db, kopi) == 10
    assert db.orders.count_documents({}) == 0


def test_harga_turun_juga_diberi_tahu(db):
    make_user(db, "budi")
    pid = add_product(db, price=5000)
    budi = login("budi")
    set_price(db, pid, 4000)
    res = place(budi, [(pid, 1, 5000)])
    assert res.status_code == 409 and "Rp4.000" in res.get_json()["error"]


# --- validasi dan replay ----------------------------------------------------
@pytest.mark.parametrize("bad", ["abc", 0, -5, 1.5, True])
def test_harga_tidak_valid_ditolak(db, bad):
    make_user(db, "budi")
    pid = add_product(db, price=5000)
    res = place(login("budi"), [(pid, 1, bad)])
    assert res.status_code == 422
    assert db.orders.count_documents({}) == 0
    assert stock_of(db, pid) == 10


def test_request_ulangan_tidak_terkena_pemeriksaan_harga(db):
    """Respons hilang di jalan, lalu harga berubah sebelum pelanggan mengulang dengan kunci yang sama:
    pesanan yang sudah dibuat dikembalikan, bukan ditolak."""
    make_user(db, "budi")
    pid = add_product(db, price=5000)
    budi = login("budi")
    key = "kunci-percobaan-0001"

    first = place(budi, [(pid, 2, 5000)], key)
    assert first.status_code == 201
    set_price(db, pid, 6000)
    again = place(budi, [(pid, 2, 5000)], key)
    assert again.status_code == 200 and again.get_json()["replayed"] is True
    assert again.get_json()["order"]["id"] == first.get_json()["order"]["id"]
    assert db.orders.count_documents({}) == 1
    assert stock_of(db, pid) == 8