"""Tes untuk perbaikan: edit stok, pesanan kedaluwarsa, nomor HP, dan ringkasan hari ini."""
import os
import sys
from datetime import timedelta

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


def make_user(db, username, role):
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


def call(client, method, path, body=None):
    return getattr(client, method)("/api" + path, json=body, headers={"X-CSRF-Token": client.csrf})


def add_product(db, stock=10, price=5000):
    now = tb.utcnow()
    return db[tb.PRODUCT_COLLECTION].insert_one({
        "name": "Teh Celup", "category": "Minuman", "price": price, "stock": stock,
        "description": "", "created_at": now, "updated_at": now}).inserted_id


def stock_of(db, pid):
    return db[tb.PRODUCT_COLLECTION].find_one({"_id": pid})["stock"]


def product_body(stock, base=None):
    body = {"name": "Teh Celup", "category": "Minuman", "price": 5000, "stock": stock, "description": ""}
    if base is not None:
        body["base_stock"] = base
    return body


# --- edit stok --------------------------------------------------------------
def test_edit_stock_keeps_sale_made_while_form_was_open(db):
    make_user(db, "admin1", "admin")
    pid = add_product(db, stock=10)
    admin = login("admin1")
    db[tb.PRODUCT_COLLECTION].update_one({"_id": pid}, {"$inc": {"stock": -3}})  # pelanggan beli 3
    res = call(admin, "put", f"/products/{pid}", product_body(stock=12, base=10))  # admin: 10 -> 12
    assert res.status_code == 200
    assert stock_of(db, pid) == 9   # 10 - 3 + 2, bukan 12


def test_edit_stock_without_base_still_overwrites(db):
    make_user(db, "admin1", "admin")
    pid = add_product(db, stock=10)
    res = call(login("admin1"), "put", f"/products/{pid}", product_body(stock=4))
    assert res.status_code == 200 and stock_of(db, pid) == 4


def test_edit_stock_conflict_when_reduction_exceeds_remaining(db):
    make_user(db, "admin1", "admin")
    pid = add_product(db, stock=10)
    admin = login("admin1")
    db[tb.PRODUCT_COLLECTION].update_one({"_id": pid}, {"$inc": {"stock": -8}})  # sisa 2
    res = call(admin, "put", f"/products/{pid}", product_body(stock=0, base=10))  # ingin -10
    assert res.status_code == 409
    assert stock_of(db, pid) == 2


def test_edit_unknown_product_is_404(db):
    make_user(db, "admin1", "admin")
    res = call(login("admin1"), "put", "/products/" + "0" * 24, product_body(stock=1, base=1))
    assert res.status_code == 404


# --- pesanan: HP dan kedaluwarsa --------------------------------------------
def order_body(pid, **extra):
    body = {"items": [{"product_id": str(pid), "qty": 2}], "address": "Jl. Melati 5, Solo",
            "phone": "0812-3456-7890"}
    body.update(extra)
    return body


def test_order_stores_normalized_phone_and_deadline(db):
    make_user(db, "budi", "user")
    pid = add_product(db, stock=5)
    res = call(login("budi"), "post", "/orders", order_body(pid))
    assert res.status_code == 201
    order = res.get_json()["order"]
    assert order["phone"] == "081234567890"
    assert order["expires_at"] > order["created_at"]
    assert stock_of(db, pid) == 3


def test_order_requires_valid_phone(db):
    make_user(db, "budi", "user")
    pid = add_product(db)
    budi = login("budi")
    body = order_body(pid)
    del body["phone"]
    assert call(budi, "post", "/orders", body).status_code == 422
    res = call(budi, "post", "/orders", order_body(pid, phone="abc"))
    assert res.status_code == 422 and "phone" in res.get_json()["fields"]


def seed_order(db, pid, status, age_hours, qty=2):
    created = tb.utcnow() - timedelta(hours=age_hours)
    return db.orders.insert_one({
        "code": f"TB-{status}-{age_hours}", "user_id": None, "username": "x",
        "items": [{"product_id": pid, "name": "Teh", "price": 5000, "qty": qty, "subtotal": 5000 * qty}],
        "total": 5000 * qty, "address": "a", "note": "", "status": status,
        "created_at": created, "updated_at": created}).inserted_id


def test_sweep_cancels_only_stale_pending_and_restores_stock(db):
    pid = add_product(db, stock=5)
    stale = seed_order(db, pid, "pending", tb.PENDING_TTL_HOURS + 1)
    fresh = seed_order(db, pid, "pending", 1)
    paid_old = seed_order(db, pid, "paid", tb.PENDING_TTL_HOURS + 48)

    assert tb.sweep_expired_orders(db, force=True) == 1
    assert db.orders.find_one({"_id": stale})["status"] == "cancelled"
    assert db.orders.find_one({"_id": stale})["cancel_reason"] == "expired"
    assert db.orders.find_one({"_id": fresh})["status"] == "pending"
    assert db.orders.find_one({"_id": paid_old})["status"] == "paid"
    assert stock_of(db, pid) == 7                       # 5 + 2 dari pesanan kedaluwarsa
    assert db.logs.find_one({"action": "pesanan_kedaluwarsa"})["actor"] == "sistem"


def test_sweep_does_not_release_stock_twice(db):
    pid = add_product(db, stock=5)
    seed_order(db, pid, "pending", tb.PENDING_TTL_HOURS + 1)
    tb.sweep_expired_orders(db, force=True)
    assert tb.sweep_expired_orders(db, force=True) == 0
    assert stock_of(db, pid) == 7


def test_sweep_is_throttled(db):
    pid = add_product(db, stock=5)
    assert tb.sweep_expired_orders(db) == 0             # pemanggilan pertama menandai waktu
    seed_order(db, pid, "pending", tb.PENDING_TTL_HOURS + 1)
    assert tb.sweep_expired_orders(db) == 0             # masih dalam jeda
    assert tb.sweep_expired_orders(db, force=True) == 1


def test_expired_stock_is_available_to_next_customer(db):
    make_user(db, "budi", "user")
    pid = add_product(db, stock=2)
    seed_order(db, pid, "pending", tb.PENDING_TTL_HOURS + 1)   # stok di DB tetap 2 (disimulasikan)
    db[tb.PRODUCT_COLLECTION].update_one({"_id": pid}, {"$set": {"stock": 0}})
    res = call(login("budi"), "post", "/orders", order_body(pid))
    assert res.status_code == 201 and stock_of(db, pid) == 0


# --- ringkasan --------------------------------------------------------------
def test_stats_today_counts_only_today_and_paid_revenue(db):
    make_user(db, "admin1", "admin")
    pid = add_product(db)
    seed_order(db, pid, "paid", 0)         # hari ini, dibayar
    seed_order(db, pid, "pending", 0)      # hari ini, belum dibayar
    seed_order(db, pid, "completed", 72)   # beberapa hari lalu
    data = call(login("admin1"), "get", "/stats").get_json()
    assert data["today"]["orders"] == 2
    assert data["today"]["revenue"] == 10000
    assert data["revenue"] == 20000


def test_products_list_reports_total(db):
    make_user(db, "budi", "user")
    add_product(db)
    data = call(login("budi"), "get", "/products").get_json()
    assert data["total"] == 1 and len(data["products"]) == 1