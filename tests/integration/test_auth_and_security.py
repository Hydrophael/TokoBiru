from tokobiru.routes import orders as orders_route
from tokobiru.services import products as products_svc
"""Unit test TokoBiru: validasi, autentikasi, otorisasi, produk, pesanan, pengguna."""
import mongomock
import pytest

import app as tokobiru
from conftest import PASSWORD

PRODUCT = {"name": "Minyak Goreng 2L", "category": "Sembako", "price": 38000, "stock": 20}
ADDRESS = "Jl. Merdeka No. 1, Ungaran"
PHONE = "081234567890"


def order_body(product, qty=1):
    return {"address": ADDRESS, "phone": PHONE, "items": [{"product_id": str(product["_id"]), "qty": qty}]}


def product_names(response):
    return [p["name"] for p in response.get_json()["products"]]


# --------------------------------------------------------------------------- #
# Sanitasi dan validasi (fungsi murni)
# --------------------------------------------------------------------------- #


class TestAuth:
    def test_daftar_membuat_role_user(self, anon, db):
        resp = anon.post("/api/auth/register", {
            "name": "Budi Santoso", "username": "Budi_01", "email": "BUDI@Contoh.id",
            "password": PASSWORD})
        assert resp.status_code == 201
        assert resp.get_json()["user"]["role"] == "user"
        saved = db.users.find_one({"username": "budi_01"})
        assert saved["email"] == "budi@contoh.id"
        assert saved["password_hash"] != PASSWORD

    def test_daftar_tidak_bisa_memilih_role(self, anon, db):
        anon.post("/api/auth/register", {
            "name": "Licik", "username": "licik", "email": "licik@contoh.id",
            "password": PASSWORD, "role": "master"})
        assert db.users.find_one({"username": "licik"})["role"] == "user"

    def test_daftar_duplikat_ditolak(self, anon, users):
        resp = anon.post("/api/auth/register", {
            "name": "Dobel", "username": "admin", "email": "lain@contoh.id", "password": PASSWORD})
        assert resp.status_code == 409

    def test_daftar_input_buruk(self, anon):
        resp = anon.post("/api/auth/register", {
            "name": "<b>x</b>", "username": "AB", "email": "bukan-email", "password": "123"})
        assert resp.status_code == 422
        assert {"username", "email", "password"} <= set(resp.get_json()["fields"])

    def test_login_dengan_username_dan_email(self, make_client, users):
        assert make_client().login("admin").status_code == 200
        assert make_client().login("admin@contoh.id").status_code == 200

    def test_login_password_salah(self, anon, users):
        assert anon.login("admin", "salah12345").status_code == 401

    def test_pesan_error_sama_untuk_akun_tidak_ada(self, anon, users):
        a = anon.login("tidakada", "apapun123").get_json()["error"]
        b = anon.login("admin", "salah12345").get_json()["error"]
        assert a == b

    def test_akun_terkunci_setelah_gagal_berulang(self, anon, users):
        for _ in range(tokobiru.MAX_FAILED_LOGIN):
            anon.login("user", "salah12345")
        assert anon.login("user", PASSWORD).status_code == 429

    def test_akun_nonaktif_tidak_bisa_masuk(self, anon, users, db):
        db.users.update_one({"username": "user"}, {"$set": {"active": False}})
        assert anon.login("user").status_code == 403

    def test_login_injection_ditolak(self, anon, users):
        resp = anon.post("/api/auth/login", {"identifier": {"$ne": ""}, "password": {"$ne": ""}})
        assert resp.status_code == 422

    def test_me_tanpa_login(self, anon):
        assert anon.get("/api/auth/me").get_json()["user"] is None

    def test_logout_mengakhiri_sesi(self, customer):
        customer.post("/api/auth/logout")
        assert customer.get("/api/orders").status_code == 401

    def test_password_tidak_bocor(self, master):
        body = master.get("/api/users").get_data(as_text=True)
        assert "password_hash" not in body


class TestKeamananRequest:
    def test_post_tanpa_csrf_ditolak(self, anon):
        resp = anon.c.post("/api/auth/login", json={"identifier": "a", "password": "b"})
        assert resp.status_code == 403

    def test_csrf_salah_ditolak(self, anon):
        anon.csrf = "palsu"
        assert anon.post("/api/auth/login", {"identifier": "a", "password": "b"}).status_code == 403

    def test_content_type_harus_json(self, anon):
        resp = anon.c.post("/api/auth/login", data="x=1", headers={"X-CSRF-Token": anon.csrf})
        assert resp.status_code == 415

    def test_header_keamanan(self, anon):
        resp = anon.get("/api/auth/me")
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Cache-Control"] == "no-store"
        assert "Content-Security-Policy" in anon.get("/").headers

    def test_endpoint_tidak_ada(self, anon):
        assert anon.get("/api/tidak-ada").status_code == 404

    def test_object_id_tidak_valid(self, admin):
        assert admin.delete("/api/products/bukan-id").status_code == 400


# --------------------------------------------------------------------------- #
# Otorisasi: multi role
# --------------------------------------------------------------------------- #
class TestOtorisasi:
    @pytest.mark.parametrize("path", [
        "/api/products", "/api/orders", "/api/stats", "/api/users", "/api/logs"])
    def test_tanpa_login_401(self, anon, path):
        assert anon.get(path).status_code == 401

    @pytest.mark.parametrize("path,allowed", [
        ("/api/products", {"user", "admin", "master"}),
        ("/api/orders", {"user", "admin", "master"}),
        ("/api/stats", {"admin", "master"}),
        ("/api/users", {"master"}),
        ("/api/logs", {"master"}),
    ])
    def test_matriks_akses(self, make_client, users, path, allowed):
        for role in ("user", "admin", "master"):
            client = make_client()
            client.login(role)
            expected = 200 if role in allowed else 403
            assert client.get(path).status_code == expected, f"{role} -> {path}"

    def test_user_tidak_bisa_kelola_produk(self, customer, product):
        assert customer.post("/api/products", PRODUCT).status_code == 403
        assert customer.put(f"/api/products/{product['_id']}", PRODUCT).status_code == 403
        assert customer.delete(f"/api/products/{product['_id']}").status_code == 403

    def test_admin_tidak_bisa_kelola_pengguna(self, admin):
        new = {"name": "Staf Baru", "username": "stafbaru", "email": "s@contoh.id",
               "password": PASSWORD, "role": "admin"}
        assert admin.post("/api/users", new).status_code == 403

    def test_admin_tidak_bisa_checkout(self, admin, product):
        assert admin.post("/api/orders", order_body(product)).status_code == 403

    def test_stats_users_hanya_untuk_master(self, admin, master):
        assert admin.get("/api/stats").get_json()["users"] is None
        assert master.get("/api/stats").get_json()["users"]["master"] == 1

    def test_akses_ditolak_tercatat_di_log(self, customer, db):
        customer.get("/api/users")
        assert db.logs.count_documents({"action": "akses_ditolak"}) == 1


# --------------------------------------------------------------------------- #
# Produk
# --------------------------------------------------------------------------- #
