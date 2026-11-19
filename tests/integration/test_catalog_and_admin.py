from bson import ObjectId
from tokobiru.services.orders import pricing
from tokobiru.routes import orders as orders_route
from tokobiru.services import products as products_svc

"""Unit test TokoBiru: validasi, autentikasi, otorisasi, produk, pesanan, pengguna."""
import pytest
from conftest import PASSWORD

import app as tokobiru

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

    def test_pencarian_dan_filter(self, admin, monkeypatch):
        # mongomock tidak mendukung $text/$meta, jadi lewati tahap indeks teks dan uji jalur regex
        monkeypatch.setattr(products_svc, "text_search_term", lambda search: "")
        admin.post("/api/products", PRODUCT)
        admin.post("/api/products", {**PRODUCT, "name": "Sabun Mandi", "category": "Rumah"})
        assert product_names(admin.get("/api/products?q=sabun")) == ["Sabun Mandi"]
        assert product_names(admin.get("/api/products?category=Sembako")) == ["Minyak Goreng 2L"]

    def test_regex_pada_pencarian_di_escape(self, admin, monkeypatch):
        # mongomock tidak mendukung $text/$meta, jadi lewati tahap indeks teks dan uji jalur regex
        monkeypatch.setattr(products_svc, "text_search_term", lambda search: "")
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
    # harga dari klien tidak pernah dipakai: yang berbeda dari database ditolak, bukan dicatat
        body = order_body(product, 1)
        body["items"][0]["price"] = 1
        assert customer.post("/api/orders", body).status_code == 409

        body["items"][0]["price"] = 65000
        assert customer.post("/api/orders", body).get_json()["order"]["total"] == 65000

    def test_stok_tidak_cukup(self, customer, product, db):
        resp = customer.post("/api/orders", order_body(product, 11))
        assert resp.status_code == 409
        assert db["master_product"].find_one({"_id": product["_id"]})["stock"] == 10

    def test_stok_dikembalikan_bila_sebagian_gagal(self, customer, product, db):
        habis = {"name": "Habis", "category": "X", "price": 1000, "stock": 0}
        db["master_product"].insert_one(habis)
        body = {"address": ADDRESS, "phone": PHONE, "items": [
            {"product_id": str(product["_id"]), "qty": 2},
            {"product_id": str(habis["_id"]), "qty": 1}]}
        assert customer.post("/api/orders", body).status_code == 409
        assert db["master_product"].find_one({"_id": product["_id"]})["stock"] == 10

    @pytest.mark.parametrize("items", [[], "x", [{"product_id": "bad", "qty": 1}], None])
    def test_keranjang_tidak_valid(self, customer, items):
        assert customer.post("/api/orders", {"address": ADDRESS, "phone": PHONE, "items": items}).status_code in (400, 422)

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

    def test_pendapatan_hari_ini_menurut_tanggal_bayar(self, customer, admin, product, db):
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        # pesanan dibuat dua hari lalu, tapi dibayar hari ini
        db.orders.update_many({}, {"$set": {"created_at": tokobiru.utcnow() - tokobiru.timedelta(days=2)}})
        admin.patch(f"/api/orders/{oid}/status", {"status": "paid"})
        today = admin.get("/api/stats").get_json()["today"]
        assert today["revenue"] == 65000
        assert today["orders"] == 0

    def test_pesanan_berjalan_tidak_tergeser_riwayat(self, customer, admin, product, db, monkeypatch):
        monkeypatch.setattr(orders_route, "ORDERS_LIMIT", 2)
        oid = customer.post("/api/orders", order_body(product)).get_json()["order"]["id"]
        admin.patch(f"/api/orders/{oid}/status", {"status": "paid"})
        now = tokobiru.utcnow()
        db.orders.update_many({}, {"$set": {"created_at": now - tokobiru.timedelta(days=30)}})
        for i in range(5):   # riwayat selesai yang lebih baru dari pesanan dibayar tadi
            db.orders.insert_one({"code": f"TB-RIWAYAT-{i}", "status": "completed", "items": [], "total": 0,
                                  "user_id": product["_id"], "username": "x", "created_at": now - tokobiru.timedelta(minutes=i)})
        statuses = [o["status"] for o in admin.get("/api/orders").get_json()["orders"]]
        assert statuses.count("paid") == 1
        assert statuses.count("completed") == 2


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

    def test_login_gagal_tidak_menyimpan_teks_akun_tidak_dikenal(self, anon, db, users):
        anon.login("rahasia99x", "apapun123")   # password yang salah diketik di kolom username
        assert "rahasia99x" not in db.logs.find_one({"action": "login_gagal"})["detail"]


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

class TestLaporanPenjualan:
    @staticmethod
    def hari_lalu(n):
        return (tokobiru.utcnow() + tokobiru.WIB_OFFSET - tokobiru.timedelta(days=n)).date().isoformat()

    @staticmethod
    def bayar(customer, admin, body):
        oid = customer.post("/api/orders", body).get_json()["order"]["id"]
        admin.patch(f"/api/orders/{oid}/status", {"status": "paid"})
        return oid

    def test_ongkir_tidak_dihitung_sebagai_omzet(self, customer, admin, product, monkeypatch):
        monkeypatch.setattr(pricing, "SHIPPING_FEE", 10000)
        self.bayar(customer, admin, order_body(product, 1))
        stats = admin.get("/api/stats").get_json()
        assert stats["revenue"] == 65000 and stats["today"]["revenue"] == 65000
        ringkasan = admin.get("/api/stats/sales").get_json()["summary"]
        assert ringkasan["revenue"] == 65000 and ringkasan["shipping"] == 10000

    def test_hanya_pesanan_dibayar_yang_dihitung(self, customer, admin, product):
        customer.post("/api/orders", order_body(product, 1))   # tetap pending
        assert admin.get("/api/stats/sales").get_json()["summary"]["orders"] == 0

    def test_rentang_tanggal_memakai_tanggal_bayar(self, customer, admin, product, db):
        lama = self.bayar(customer, admin, order_body(product, 1))
        self.bayar(customer, admin, order_body(product, 2))
        db.orders.update_one({"_id": ObjectId(lama)},
                             {"$set": {"paid_at": tokobiru.utcnow() - tokobiru.timedelta(days=40)}})
        bawaan = admin.get("/api/stats/sales").get_json()
        assert bawaan["summary"]["orders"] == 1 and bawaan["summary"]["revenue"] == 130000
        assert len(bawaan["series"]) == 30 and bawaan["group"] == "day"
        luas = admin.get(f"/api/stats/sales?from={self.hari_lalu(45)}").get_json()
        assert luas["summary"]["orders"] == 2 and luas["summary"]["items"] == 3

    def test_omzet_per_bulan_dan_batas_grafik_harian(self, customer, admin, product):
        self.bayar(customer, admin, order_body(product, 1))
        bulanan = admin.get(f"/api/stats/sales?from={self.hari_lalu(45)}&group=month").get_json()
        assert bulanan["group"] == "month" and all(len(p["key"]) == 7 for p in bulanan["series"])
        assert sum(p["revenue"] for p in bulanan["series"]) == 65000
        panjang = admin.get(f"/api/stats/sales?from={self.hari_lalu(120)}&group=day").get_json()
        assert panjang["group"] == "month"

    def test_produk_terlaris_urut_jumlah_terjual(self, customer, admin, product, db):
        teh = db["master_product"].insert_one({"name": "Teh Botol", "category": "Minuman", "price": 5000, "stock": 50}).inserted_id
        body = {"address": ADDRESS, "phone": PHONE,
                "items": [{"product_id": str(product["_id"]), "qty": 1}, {"product_id": str(teh), "qty": 5}]}
        self.bayar(customer, admin, body)
        top = admin.get("/api/stats/sales").get_json()["top_products"]
        assert [(p["name"], p["qty"], p["revenue"]) for p in top] == [("Teh Botol", 5, 25000), ("Beras 5kg", 1, 65000)]

    @pytest.mark.parametrize("query", [
        "from=abc", "from=2026-12-01&to=2026-11-01", "from=2020-01-01&to=2026-11-01"])
    def test_rentang_tidak_valid_422(self, admin, query):
        assert admin.get(f"/api/stats/sales?{query}").status_code == 422
