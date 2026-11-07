"""Tes untuk indeks pesanan berdasarkan created_at dan batas pesanan pending per pelanggan."""
import os
import sys
from datetime import timedelta

import mongomock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as tb  # noqa: E402

LIMIT = 2


@pytest.fixture
def db(monkeypatch):
    database = mongomock.MongoClient().tokobiru
    monkeypatch.setattr(tb, "_db", database)
    monkeypatch.setattr(tb, "_last_sweep", None)
    monkeypatch.setattr(tb, "MAX_PENDING_ORDERS", LIMIT)
    return database


def make_user(db, username, role="user"):
    db.users.insert_one(tb.new_user_doc({
        "name": username.title(), "username": username,
        "email": f"{username}@t.test", "password": "rahasia123"}, role))
    return db.users.find_one({"username": username})["_id"]


def login(username):
    client = tb.app.test_client()
    csrf = client.get("/api/auth/me").get_json()["csrf"]
    res = client.post("/api/auth/login", json={"identifier": username, "password": "rahasia123"},
                      headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200, res.get_json()
    client.csrf = res.get_json()["csrf"]
    return client


def add_product(db, stock=10, price=5000):
    now = tb.utcnow()
    return db[tb.PRODUCT_COLLECTION].insert_one({
        "name": "Teh Celup", "category": "Minuman", "price": price, "stock": stock,
        "description": "", "created_at": now, "updated_at": now}).inserted_id


def stock_of(db, pid):
    return db[tb.PRODUCT_COLLECTION].find_one({"_id": pid})["stock"]


def place(client, pid, key=None, qty=1):
    headers = {"X-CSRF-Token": client.csrf}
    if key is not None:
        headers["Idempotency-Key"] = key
    body = {"items": [{"product_id": str(pid), "qty": qty}],
            "address": "Jl. Melati 5, Solo", "phone": "081234567890"}
    return client.post("/api/orders", json=body, headers=headers)


def seed_stale_pending(db, user_id, pid, n):
    """Pesanan pending yang sudah lewat batas bayar (stok sudah terpotong di DB, seperti aslinya)."""
    created = tb.utcnow() - timedelta(hours=tb.PENDING_TTL_HOURS + 1)
    for i in range(n):
        db.orders.insert_one({
            "code": f"TB-LAMA-{i}", "user_id": user_id, "username": "budi",
            "items": [{"product_id": pid, "name": "Teh", "price": 5000, "qty": 1, "subtotal": 5000}],
            "total": 5000, "address": "a", "note": "", "status": "pending",
            "created_at": created, "updated_at": created})


# --- indeks -----------------------------------------------------------------
def test_indeks_created_at_dibuat(db):
    tb.ensure_indexes(db)
    keys = [[tuple(pair) for pair in spec["key"]] for spec in db.orders.index_information().values()]
    assert [("created_at", -1)] in keys


# --- batas pesanan pending --------------------------------------------------
def test_pesanan_ditolak_bila_batas_tercapai(db):
    make_user(db, "budi")
    pid = add_product(db, stock=10)
    budi = login("budi")
    for _ in range(LIMIT):
        assert place(budi, pid).status_code == 201

    res = place(budi, pid)
    assert res.status_code == 429          # bukan 409: frontend menganggap 409 konflik stok
    assert "belum dibayar" in res.get_json()["error"]
    assert db.orders.count_documents({}) == LIMIT
    assert stock_of(db, pid) == 10 - LIMIT  # pesanan yang ditolak tidak memotong stok


def test_batas_berlaku_per_pelanggan(db):
    make_user(db, "budi")
    make_user(db, "siti")
    pid = add_product(db, stock=10)
    budi = login("budi")
    for _ in range(LIMIT):
        place(budi, pid)
    assert place(budi, pid).status_code == 429
    assert place(login("siti"), pid).status_code == 201


def test_pesanan_dibatalkan_membebaskan_slot(db):
    make_user(db, "budi")
    pid = add_product(db, stock=10)
    budi = login("budi")
    first = place(budi, pid).get_json()["order"]
    place(budi, pid)
    assert place(budi, pid).status_code == 429

    res = budi.patch(f"/api/orders/{first['id']}/status", json={"status": "cancelled"},
                     headers={"X-CSRF-Token": budi.csrf})
    assert res.status_code == 200
    assert place(budi, pid).status_code == 201


def test_pesanan_dibayar_tidak_dihitung(db):
    make_user(db, "budi")
    pid = add_product(db, stock=10)
    budi = login("budi")
    place(budi, pid)
    place(budi, pid)
    db.orders.update_one({}, {"$set": {"status": "paid"}})   # admin mengonfirmasi satu pesanan
    assert place(budi, pid).status_code == 201


def test_pesanan_kedaluwarsa_tidak_dihitung(db):
    budi_id = make_user(db, "budi")
    pid = add_product(db, stock=10)
    seed_stale_pending(db, budi_id, pid, LIMIT)
    # penyapuan di orders_create membatalkan pesanan lama sebelum batas dicek
    assert place(login("budi"), pid).status_code == 201
    assert stock_of(db, pid) == 10 + LIMIT - 1


def test_request_ulangan_tetap_dibalas_saat_batas_tercapai(db, monkeypatch):
    monkeypatch.setattr(tb, "MAX_PENDING_ORDERS", 1)
    make_user(db, "budi")
    pid = add_product(db, stock=10)
    budi = login("budi")
    key = "kunci-percobaan-0001"

    assert place(budi, pid, key).status_code == 201
    replay = place(budi, pid, key)         # pesanan itu sendiri yang memenuhi batas
    assert replay.status_code == 200 and replay.get_json()["replayed"] is True
    assert place(budi, pid, "kunci-percobaan-0002").status_code == 429
    assert db.orders.count_documents({}) == 1