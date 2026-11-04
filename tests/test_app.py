"""Unit test TokoBiru: validasi, autentikasi, otorisasi, produk, pesanan, pengguna."""
import mongomock
import pytest

import app as tokobiru
from conftest import PASSWORD

PRODUCT = {"name": "Minyak Goreng 2L", "category": "Sembako", "price": 38000, "stock": 20}
ADDRESS = "Jl. Merdeka No. 1, Ungaran"


def order_body(product, qty=1):
    return {"address": ADDRESS, "items": [{"product_id": str(product["_id"]), "qty": qty}]}


def product_names(response):
    return [p["name"] for p in response.get_json()["products"]]


# --------------------------------------------------------------------------- #
# Sanitasi dan validasi (fungsi murni)
# --------------------------------------------------------------------------- #
class TestSanitize:
    def test_tag_html_dibuang(self):
        assert tokobiru.sanitize("<script>alert(1)</script>Halo") == "alert(1)Halo"

    def test_spasi_dirapikan(self):
        assert tokobiru.sanitize("  a   b \t c ") == "a b c"

    def test_karakter_kontrol_dibuang(self):
        assert tokobiru.sanitize("ab\x00c\x07d") == "abcd"

    def test_unicode_dinormalisasi(self):
        assert tokobiru.sanitize("ＡＢＣ") == "ABC"

    def test_multiline_menjaga_baris_baru(self):
        assert tokobiru.sanitize("a\n\n\n\nb", multiline=True) == "a\n\nb"


class TestParseInt:
    @pytest.mark.parametrize("raw,expected", [(5, 5), ("12", 12), (" 7 ", 7), (3.0, 3), ("-4", -4)])
    def test_valid(self, raw, expected):
        assert tokobiru.parse_int(raw) == expected

    @pytest.mark.parametrize("raw", ["abc", "1.5", 2.5, None, "", "1e3", {"$gt": 0}, ["1"]])
    def test_tidak_valid(self, raw):
        assert tokobiru.parse_int(raw) is None


class TestPassword:
    @pytest.mark.parametrize("pw,ok", [
        ("abc12345", True), ("pendek1", False), ("hanyahuruf", False), ("12345678", False)])
    def test_kebijakan(self, pw, ok):
        assert tokobiru.is_strong_password(pw) is ok


class TestForm:
    def test_nosql_injection_ditolak(self):
        form = tokobiru.Form({"name": {"$ne": ""}})
        form.text("name", "Nama")
        assert "name" in form.errors

    def test_bool_bukan_integer(self):
        form = tokobiru.Form({"qty": True})
        form.integer("qty", "Jumlah", 1, 99)
        assert "qty" in form.errors

    def test_batas_integer(self):
        form = tokobiru.Form({"qty": 100})
        form.integer("qty", "Jumlah", 1, 99)
        assert "antara" in form.errors["qty"]

    def test_pilihan_di_luar_daftar(self):
        form = tokobiru.Form({"role": "master"})
        form.choice("role", "Role", tokobiru.ASSIGNABLE_ROLES)
        assert "role" in form.errors

    def test_error_dikumpulkan_sekaligus(self):
        with pytest.raises(tokobiru.ApiError) as exc:
            tokobiru.user_form({"name": "", "username": "A!", "email": "x", "password": "1"})
        assert {"name", "username", "email", "password"} <= set(exc.value.fields)


# --------------------------------------------------------------------------- #
# Collection dan index MongoDB
# --------------------------------------------------------------------------- #
class TestDatabase:
    def test_produk_disimpan_di_master_product(self, db, admin):
        assert admin.post("/api/products", PRODUCT).status_code == 201
        assert db["master_product"].count_documents({}) == 1
        assert "products" not in db.list_collection_names()

    def test_index_dibuat(self, db):
        users_idx = db.users.index_information()
        assert any(v.get("unique") and v["key"] == [("username", 1)] for v in users_idx.values())
        assert any(v.get("unique") and v["key"] == [("email", 1)] for v in users_idx.values())
        prod_keys = [v["key"] for v in db["master_product"].index_information().values()]
        assert [("name", 1)] in prod_keys and [("category", 1)] in prod_keys

    def test_migrasi_collection_lama(self):
        db = mongomock.MongoClient()["migrasi"]  # database baru, belum ada master_product
        db["products"].insert_one({"name": "Lama", "category": "X", "price": 100, "stock": 1})
        tokobiru.migrate_legacy_collections(db)
        assert "products" not in db.list_collection_names()
        assert db["master_product"].count_documents({"name": "Lama"}) == 1


# --------------------------------------------------------------------------- #
# Autentikasi
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
class TestProduk:
    def test_admin_crud(self, admin):
        created = admin.post("/api/products", PRODUCT)
        assert created.status_code == 201
        pid = created.get_json()["product"]["id"]
        changed = admin.put(f"/api/products/{pid}", {**PRODUCT, "price": 40000})
        assert changed.get_json()["product"]["price"] == 40000
        assert admin.delete(f"/api/products/{pid}").status_code == 200
        assert admin.delete(f"/api/products/{pid}").status_code == 404

    @pytest.mark.parametrize("override", [
        {"price": -500}, {"price": 50}, {"price": "abc"}, {"stock": -1},
        {"stock": 1.5}, {"name": ""}, {"name": "x"}, {"category": ""}, {"price": {"$gt": 0}}])
    def test_validasi_produk(self, admin, override):
        assert admin.post("/api/products", {**PRODUCT, **override}).status_code == 422

    def test_nama_produk_disanitasi(self, admin, db):
        admin.post("/api/products", {**PRODUCT, "name": "<img src=x onerror=alert(1)>Gula"})
        assert db["master_product"].find_one()["name"] == "Gula"

    def test_pencarian_dan_filter(self, admin):
        admin.post("/api/products", PRODUCT)
        admin.post("/api/products", {**PRODUCT, "name": "Sabun Mandi", "category": "Rumah"})
        assert product_names(admin.get("/api/products?q=sabun")) == ["Sabun Mandi"]
        assert product_names(admin.get("/api/products?category=Sembako")) == ["Minyak Goreng 2L"]

    def test_regex_pada_pencarian_di_escape(self, admin):
        admin.post("/api/products", PRODUCT)
        assert admin.get("/api/products?q=.*").get_json()["products"] == []


# --------------------------------------------------------------------------- #
# Pesanan
# --------------------------------------------------------------------------- #
class TestPesanan:
    def test_checkout_mengurangi_stok(self, customer, product, db):
        resp = customer.post("/api/orders", order_body(product, 3))
        assert resp.status_code == 201
        order = resp.get_json()["order"]
        assert order["status"] == "pending"
        assert order["total"] == 3 * 65000
        assert db["master_product"].find_one({"_id": product["_id"]})["stock"] == 7

    def test_harga_diambil_dari_server(self, customer, product):
        body = order_body(product, 1)
        body["items"][0]["price"] = 1
        assert customer.post("/api/orders", body).get_json()["order"]["total"] == 65000

    def test_stok_tidak_cukup(self, customer, product, db):
        resp = customer.post("/api/orders", order_body(product, 11))
        assert resp.status_code == 409
        assert db["master_product"].find_one({"_id": product["_id"]})["stock"] == 10

    def test_stok_dikembalikan_bila_sebagian_gagal(self, customer, product, db):
        habis = {"name": "Habis", "category": "X", "price": 1000, "stock": 0}
        db["master_product"].insert_one(habis)
        body = {"address": ADDRESS, "items": [
            {"product_id": str(product["_id"]), "qty": 2},
            {"product_id": str(habis["_id"]), "qty": 1}]}
        assert customer.post("/api/orders", body).status_code == 409
        assert db["master_product"].find_one({"_id": product["_id"]})["stock"] == 10

    @pytest.mark.parametrize("items", [[], "x", [{"product_id": "bad", "qty": 1}], None])
    def test_keranjang_tidak_valid(self, customer, items):
        assert customer.post("/api/orders", {"address": ADDRESS, "items": items}).status_code in (400, 422)

    @pytest.mark.parametrize("qty", [0, -1, 100, "abc"])
    def test_jumlah_tidak_valid(self, customer, product, qty):
        body = order_body(product)
        body["items"][0]["qty"] = qty
        assert customer.post("/api/orders", body).status_code == 422

    def test_alamat_wajib(self, customer, product):
        body = order_body(product)
        body["address"] = ""
        assert customer.post("/api/orders", body).status_code == 422

    def test_user_hanya_melihat_pesanan_sendiri(self, customer, other_customer, product):
        customer.post("/api/orders", order_body(product))
        assert other_customer.get("/api/orders").get_json()["orders"] == []
        assert len(customer.get("/api/orders").get_json()["orders"]) == 1

    def test_staf_melihat_semua_pesanan(self, customer, admin, product):
        customer.post("/api/orders", order_body(product))
        assert len(admin.get("/api/orders").get_json()["orders"]) == 1

    def test_alur_lengkap(self, customer, admin, product):
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        for status in ("paid", "shipped"):
            assert admin.patch(f"/api/orders/{oid}/status", {"status": status}).status_code == 200
        done = customer.patch(f"/api/orders/{oid}/status", {"status": "completed"})
        assert done.get_json()["order"]["status"] == "completed"

    def test_staf_tidak_boleh_loncat_status(self, customer, admin, product):
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        assert admin.patch(f"/api/orders/{oid}/status", {"status": "completed"}).status_code == 422

    def test_user_tidak_boleh_konfirmasi_bayar(self, customer, product):
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        assert customer.patch(f"/api/orders/{oid}/status", {"status": "paid"}).status_code == 403

    def test_batal_mengembalikan_stok(self, customer, product, db):
        oid = customer.post("/api/orders", order_body(product, 4)).get_json()["order"]["id"]
        assert customer.patch(f"/api/orders/{oid}/status", {"status": "cancelled"}).status_code == 200
        assert db["master_product"].find_one({"_id": product["_id"]})["stock"] == 10

    def test_user_tidak_bisa_ubah_pesanan_orang_lain(self, customer, other_customer, product):
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        resp = other_customer.patch(f"/api/orders/{oid}/status", {"status": "cancelled"})
        assert resp.status_code == 404

    def test_status_tidak_dikenal(self, customer, product):
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        assert customer.patch(f"/api/orders/{oid}/status", {"status": "hacked"}).status_code == 422


class TestRingkasan:
    def test_pendapatan_hanya_dari_pesanan_dibayar(self, customer, admin, product):
        a = customer.post("/api/orders", order_body(product, 1)).get_json()["order"]["id"]
        customer.post("/api/orders", order_body(product, 2))  # tetap pending
        admin.patch(f"/api/orders/{a}/status", {"status": "paid"})
        data = admin.get("/api/stats").get_json()
        assert data["revenue"] == 65000
        assert data["orders"]["total"] == 2 and data["orders"]["pending"] == 1

    def test_stok_menipis(self, admin, product, db):
        db["master_product"].update_one({"_id": product["_id"]}, {"$set": {"stock": 2}})
        assert len(admin.get("/api/stats").get_json()["low_stock"]) == 1


# --------------------------------------------------------------------------- #
# Manajemen pengguna (master)
# --------------------------------------------------------------------------- #
class TestPengguna:
    NEW = {"name": "Staf Baru", "username": "stafbaru", "email": "staf@contoh.id",
           "password": PASSWORD, "role": "admin"}

    def test_master_membuat_admin(self, master, db):
        assert master.post("/api/users", self.NEW).status_code == 201
        assert db.users.find_one({"username": "stafbaru"})["role"] == "admin"

    def test_master_tidak_bisa_membuat_master(self, master):
        assert master.post("/api/users", {**self.NEW, "role": "master"}).status_code == 422

    def test_username_duplikat(self, master):
        master.post("/api/users", self.NEW)
        assert master.post("/api/users", self.NEW).status_code == 409

    def test_ubah_role_dan_nonaktifkan(self, master, users):
        uid = str(users["user"]["_id"])
        assert master.patch(f"/api/users/{uid}", {"role": "admin"}).get_json()["user"]["role"] == "admin"
        assert master.patch(f"/api/users/{uid}", {"active": False}).get_json()["user"]["active"] is False

    def test_akun_master_dilindungi(self, master, users):
        uid = str(users["master"]["_id"])
        assert master.patch(f"/api/users/{uid}", {"role": "user"}).status_code == 403
        assert master.delete(f"/api/users/{uid}").status_code == 403

    def test_hapus_pengguna(self, master, users):
        uid = str(users["user"]["_id"])
        assert master.delete(f"/api/users/{uid}").status_code == 200
        assert master.delete(f"/api/users/{uid}").status_code == 404

    def test_tanpa_perubahan_ditolak(self, master, users):
        assert master.patch(f"/api/users/{users['user']['_id']}", {}).status_code == 422

    def test_pengguna_nonaktif_kehilangan_sesi(self, make_client, master, users):
        cust = make_client()
        cust.login("user")
        master.patch(f"/api/users/{users['user']['_id']}", {"active": False})
        assert cust.get("/api/orders").status_code == 401


class TestLog:
    def test_aktivitas_tercatat(self, master, admin):
        admin.post("/api/products", PRODUCT)
        actions = [row["action"] for row in master.get("/api/logs").get_json()["logs"]]
        assert "produk_tambah" in actions and "login" in actions

    def test_login_gagal_tercatat(self, anon, db, users):
        anon.login("admin", "salah12345")
        assert db.logs.count_documents({"action": "login_gagal"}) == 1


class TestBootstrap:
    def test_master_dibuat_dari_env(self, db, monkeypatch):
        monkeypatch.setenv("MASTER_USERNAME", "Bos")
        monkeypatch.setenv("MASTER_EMAIL", "bos@contoh.id")
        monkeypatch.setenv("MASTER_PASSWORD", PASSWORD)
        tokobiru.bootstrap(db)
        tokobiru.bootstrap(db)  # kedua kali tidak membuat dobel
        assert db.users.count_documents({"role": "master"}) == 1


class TestSeedDemo:
    def test_akun_demo_tiap_role_dan_idempoten(self, db, anon):
        first = tokobiru.seed_demo(db)
        assert len(first) == 3 and tokobiru.seed_demo(db) == []
        assert db["master_product"].count_documents({}) == len(tokobiru.DEMO_PRODUCTS)
        for _, username, _, role in tokobiru.DEMO_USERS:
            assert db.users.find_one({"username": username})["role"] == role
        assert anon.login("master_demo", tokobiru.DEMO_PASSWORD).status_code == 200