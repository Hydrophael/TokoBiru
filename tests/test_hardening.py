"""Tes perbaikan Prioritas 1: env kosong, kode pesanan unik, kunci idempotensi, header cache statis."""
import itertools
import re

import mongomock
import pytest
from pymongo.errors import DuplicateKeyError

import app as tokobiru

ADDRESS = "Jl. Merdeka No. 1, Ungaran"
PHONE = "081234567890"
KEY = "kunci-percobaan-0001"


def order_body(product, qty=2):
    return {"address": ADDRESS, "phone": PHONE, "items": [{"product_id": str(product["_id"]), "qty": qty}]}


def place(client, product, key=None, qty=2):
    """POST /api/orders dengan header Idempotency-Key opsional (Client bawaan conftest tidak mendukungnya)."""
    headers = client._headers()
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.c.post("/api/orders", json=order_body(product, qty), headers=headers)


def stock_of(db, product):
    return db[tokobiru.PRODUCT_COLLECTION].find_one({"_id": product["_id"]})["stock"]


# --------------------------------------------------------------------------- #
# Environment variable kosong (mis. .env.example yang disalin apa adanya)
# --------------------------------------------------------------------------- #
class TestEnv:
    @pytest.mark.parametrize("raw, expected", [("", "tokobiru"), ("   ", "tokobiru"), (" toko_lain ", "toko_lain")])
    def test_nama_database_kosong_memakai_default(self, monkeypatch, raw, expected):
        monkeypatch.setenv("MONGO_DB", raw)
        assert tokobiru.mongo_db_name() == expected

    def test_nama_database_tidak_diisi(self, monkeypatch):
        monkeypatch.delenv("MONGO_DB", raising=False)
        assert tokobiru.mongo_db_name() == "tokobiru"

    def test_strip_dimatikan_untuk_rahasia(self, monkeypatch):
        monkeypatch.setenv("RAHASIA_UJI", "  spasi di tepi  ")
        assert tokobiru._env_str("RAHASIA_UJI", strip=False) == "  spasi di tepi  "
        assert tokobiru._env_str("RAHASIA_UJI") == "spasi di tepi"

    @pytest.mark.parametrize("raw, expected", [("", 24), ("5", 5), ("0", 1), ("abc", 24)])
    def test_env_int(self, monkeypatch, raw, expected):
        monkeypatch.setenv("TTL_UJI", raw)
        assert tokobiru._env_int("TTL_UJI", 24) == expected

    def test_master_dengan_nama_kosong_memakai_nama_default(self, db, monkeypatch):
        for key, value in {"MASTER_USERNAME": "bos", "MASTER_EMAIL": "bos@contoh.id",
                           "MASTER_PASSWORD": "rahasia123", "MASTER_NAME": ""}.items():
            monkeypatch.setenv(key, value)
        tokobiru.bootstrap(db)
        master = db.users.find_one({"username": "bos"})
        assert master["role"] == "master" and master["name"] == "Master"


# --------------------------------------------------------------------------- #
# Kode pesanan
# --------------------------------------------------------------------------- #
class TestKodePesanan:
    def test_format_kode(self):
        assert re.fullmatch(r"TB-\d{6}-[A-HJKMNP-Z2-9]{6}", tokobiru.new_order_code())

    def test_tanpa_karakter_yang_mudah_tertukar(self):
        suffixes = "".join(tokobiru.new_order_code().rsplit("-", 1)[1] for _ in range(300))
        assert not set(suffixes) & set("01ILO")

    def test_indeks_kode_unik(self, db):
        db.orders.insert_one({"code": "TB-DUP"})
        with pytest.raises(DuplicateKeyError):
            db.orders.insert_one({"code": "TB-DUP"})

    def test_kode_bentrok_diundi_ulang(self, customer, product, db, monkeypatch):
        db.orders.insert_one({"code": "TB-DUP"})
        codes = iter(["TB-DUP", "TB-DUP", "TB-BARU"])
        monkeypatch.setattr(tokobiru, "new_order_code", lambda: next(codes))
        resp = place(customer, product)
        assert resp.status_code == 201
        assert resp.get_json()["order"]["code"] == "TB-BARU"
        assert stock_of(db, product) == 8

    def test_gagal_bersih_bila_kode_terus_bentrok(self, customer, product, db, monkeypatch):
        db.orders.insert_one({"code": "TB-DUP"})
        monkeypatch.setattr(tokobiru, "new_order_code", lambda: "TB-DUP")
        resp = place(customer, product)
        assert resp.status_code == 503
        assert stock_of(db, product) == 10                 # stok dikembalikan
        assert db.orders.count_documents({}) == 1          # tidak ada pesanan baru

    def test_data_lama_dengan_kode_ganda_tidak_menggagalkan_start(self):
        fake = mongomock.MongoClient()["tokobiru_lama"]
        # user_id dibedakan: mongomock (berbeda dari MongoDB asli) tidak menerapkan filter parsial saat
        # membangun indeks di atas dokumen yang sudah ada, sehingga indeks idem_key ikut bentrok
        fake.orders.insert_many([{"code": "TB-LAMA", "user_id": 1}, {"code": "TB-LAMA", "user_id": 2}])
        tokobiru.ensure_indexes(fake)                      # tidak boleh melempar error
        assert fake.users.index_information()              # indeks lain tetap dibuat


# --------------------------------------------------------------------------- #
# Kunci idempotensi: mencegah pesanan ganda
# --------------------------------------------------------------------------- #
class TestIdempotensi:
    def test_kunci_sama_hanya_membuat_satu_pesanan(self, customer, product, db):
        first = place(customer, product, KEY)
        second = place(customer, product, KEY)
        assert (first.status_code, second.status_code) == (201, 200)
        assert second.get_json()["replayed"] is True
        assert first.get_json()["order"]["id"] == second.get_json()["order"]["id"]
        assert db.orders.count_documents({}) == 1
        assert stock_of(db, product) == 8                  # stok dipotong sekali saja

    def test_tanpa_kunci_tiap_request_membuat_pesanan(self, customer, product, db):
        assert place(customer, product).status_code == 201
        assert place(customer, product).status_code == 201
        assert db.orders.count_documents({}) == 2
        assert stock_of(db, product) == 6

    def test_kunci_sama_untuk_isi_berbeda_ditolak(self, customer, product, db):
        assert place(customer, product, KEY, qty=2).status_code == 201
        resp = place(customer, product, KEY, qty=3)
        assert resp.status_code == 422
        assert db.orders.count_documents({}) == 1
        assert stock_of(db, product) == 8

    def test_kunci_berlaku_per_pelanggan(self, customer, other_customer, product, db):
        assert place(customer, product, KEY).status_code == 201
        assert place(other_customer, product, KEY).status_code == 201
        assert db.orders.count_documents({}) == 2

    @pytest.mark.parametrize("key", ["pendek", "ada spasi di dalam", "x" * 65, "tanda!seru_ok"])
    def test_kunci_tidak_valid_ditolak(self, customer, product, db, key):
        assert place(customer, product, key).status_code == 422
        assert stock_of(db, product) == 10

    def test_kunci_tidak_ikut_dikirim_ke_klien(self, customer, product):
        order = place(customer, product, KEY).get_json()["order"]
        assert "idem_key" not in order
        listed = customer.get("/api/orders").get_json()["orders"]
        assert all("idem_key" not in o for o in listed)

    def test_request_kembar_bersamaan(self, customer, product, db, monkeypatch):
        """Request kedua lolos pengecekan awal (belum ada pesanan) lalu bentrok saat menyimpan."""
        assert place(customer, product, KEY).status_code == 201
        monkeypatch.setattr(tokobiru, "replayed_order", lambda *args: None)   # meniru pengecekan yang kalah balapan
        resp = place(customer, product, KEY)
        assert resp.status_code == 200 and resp.get_json()["replayed"] is True
        assert db.orders.count_documents({}) == 1
        assert stock_of(db, product) == 8                  # stok yang sempat dipotong dikembalikan


# --------------------------------------------------------------------------- #
# Cache file statis
# --------------------------------------------------------------------------- #
class TestCacheStatis:
    @pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/core.js", "/static/style.css"])
    def test_wajib_validasi_ulang(self, anon, path):
        resp = anon.get(path)
        assert resp.status_code == 200
        assert "no-cache" in resp.headers["Cache-Control"]

    def test_file_tidak_berubah_dibalas_304(self, anon):
        etag = anon.get("/static/app.js").headers["ETag"]
        resp = anon.c.get("/static/app.js", headers={"If-None-Match": etag})
        assert resp.status_code == 304