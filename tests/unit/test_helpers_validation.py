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
