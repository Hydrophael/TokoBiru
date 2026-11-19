"""Tes untuk empat perbaikan: argumen CLI di app.py, indeks TTL log, CSP blob:, dan webhook refund yang idempotent."""
import sys

import pytest
from pymongo.errors import OperationFailure

import app
from tokobiru.core import connection
from tokobiru.core.util import utcnow
from tokobiru.routes import payments

WEBHOOK_TOKEN = "token-uji-123"
ORDER_CODE = "TB-261119-ABC234"


# --- 1. app.py meneruskan argumen ke cli.py ---

class TestEntryPoint:
    def test_argumen_diteruskan_ke_cli_dan_server_tidak_jalan(self, monkeypatch):
        import cli
        dipanggil = []
        monkeypatch.setattr(sys, "argv", ["app.py", "seed-demo"])
        monkeypatch.setattr(cli, "main", lambda: dipanggil.append(sys.argv[1]))
        monkeypatch.setattr(app.app, "run", lambda *a, **k: pytest.fail("server tidak boleh jalan"))
        app.main()
        assert dipanggil == ["seed-demo"]

    def test_perintah_gen_vapid_jalan_lewat_app_py(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["app.py", "gen-vapid"])
        monkeypatch.setattr(app.app, "run", lambda *a, **k: pytest.fail("server tidak boleh jalan"))
        app.main()
        out = capsys.readouterr().out
        assert "VAPID_PUBLIC_KEY=" in out and "VAPID_PRIVATE_KEY=" in out

    def test_tanpa_argumen_menjalankan_server(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["app.py"])
        monkeypatch.delenv("PORT", raising=False)
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        dipanggil = {}
        monkeypatch.setattr(app.app, "run", lambda **kwargs: dipanggil.update(kwargs))
        app.main()
        assert dipanggil == {"host": "127.0.0.1", "port": 5000, "debug": False}


# --- 2. indeks TTL log ikut lama simpan dari konfigurasi, dan tidak menjatuhkan koneksi bila bentrok ---

class _FakeDatabase:
    def __init__(self):
        self.commands = []

    def command(self, *args, **kwargs):
        self.commands.append((args, kwargs))


class _ConflictingCollection:
    name = "logs"

    def __init__(self):
        self.database = _FakeDatabase()

    def create_index(self, keys, **kwargs):
        raise OperationFailure("Index already exists with different options", code=85)


class TestIndeksLog:
    def test_indeks_log_memakai_lama_simpan_dari_konfigurasi(self, db):
        info = db.logs.index_information()
        assert info["logs_ttl"]["expireAfterSeconds"] == connection.LOG_RETENTION_DAYS * 86400

    def test_ensure_indexes_dua_kali_tidak_error(self, db):
        connection.ensure_indexes(db)
        assert "logs_ttl" in db.logs.index_information()

    def test_bentrok_opsi_memperbarui_lewat_collmod(self):
        coll = _ConflictingCollection()
        connection.ensure_ttl_index(coll, "ts", 30, "logs_ttl")
        assert coll.database.commands == [
            (("collMod", "logs"), {"index": {"name": "logs_ttl", "expireAfterSeconds": 30 * 86400}})]

    def test_gagal_memperbarui_hanya_dicatat_tidak_dilempar(self):
        coll = _ConflictingCollection()
        coll.database.command = lambda *a, **k: (_ for _ in ()).throw(OperationFailure("gagal", code=27))
        connection.ensure_ttl_index(coll, "ts", 30, "logs_ttl")   # tidak boleh melempar


# --- 3. CSP: foto yang dikecilkan lewat blob: tidak diblokir, aturan skrip tetap ketat ---

class TestCsp:
    def test_img_src_mengizinkan_blob(self, anon):
        csp = anon.get("/").headers["Content-Security-Policy"]
        assert "img-src 'self' data: blob:;" in csp

    def test_skrip_tetap_hanya_dari_domain_sendiri(self, anon):
        csp = anon.get("/").headers["Content-Security-Policy"]
        assert "script-src 'self';" in csp
        assert "connect-src 'self';" in csp
        assert "unsafe-eval" not in csp
        assert "script-src 'self' 'unsafe-inline'" not in csp


# --- 4. webhook Xendit: refund terlambat ditandai dan diberitahukan sekali saja ---

@pytest.fixture()
def xendit(monkeypatch):
    monkeypatch.setattr(payments, "XENDIT_ENABLED", True)
    monkeypatch.setattr(payments, "XENDIT_CALLBACK_TOKEN", WEBHOOK_TOKEN)


def _order(db, users, status, **extra):
    now = utcnow()
    doc = {"user_id": users["user"]["_id"], "username": "user", "code": ORDER_CODE, "items": [],
           "subtotal": 50000, "shipping_fee": 0, "total": 50000, "payment_method": "qris", "cod": False,
           "status": status, "created_at": now, "updated_at": now, "qr_id": "qr_uji_1", **extra}
    db.orders.insert_one(doc)
    return doc


def _bayar(anon, amount=50000, token=WEBHOOK_TOKEN):
    body = {"event": "qr.payment", "data": {"reference_id": ORDER_CODE, "status": "COMPLETED",
                                            "amount": amount, "qr_id": "qr_uji_1"}}
    return anon.c.post("/webhooks/xendit", json=body, headers={"x-callback-token": token})


class TestWebhookXendit:
    def test_token_salah_ditolak(self, db, users, xendit, anon):
        _order(db, users, "pending")
        assert _bayar(anon, token="salah").status_code == 401
        assert db.orders.find_one({"code": ORDER_CODE})["status"] == "pending"

    def test_nonaktif_tanpa_kunci_xendit(self, db, users, anon):
        assert _bayar(anon).status_code == 404

    def test_pembayaran_normal_melunasi_pesanan_sekali(self, db, users, xendit, anon):
        _order(db, users, "pending")
        assert _bayar(anon).status_code == 200
        assert _bayar(anon).status_code == 200   # kiriman ulang
        order = db.orders.find_one({"code": ORDER_CODE})
        assert order["status"] == "paid" and order["paid_via"] == "xendit"
        assert db.logs.count_documents({"action": "pesanan_status"}) == 1

    def test_bayar_setelah_batal_ditandai_refund(self, db, users, xendit, anon):
        _order(db, users, "cancelled")
        assert _bayar(anon).status_code == 200
        assert db.orders.find_one({"code": ORDER_CODE})["needs_refund"] is True
        assert db.logs.count_documents({"action": "pembayaran_terlambat"}) == 1
        assert db.notifications.count_documents({"title": "Perlu refund"}) >= 1

    def test_kiriman_ulang_tidak_mengulang_audit_dan_kabar(self, db, users, xendit, anon):
        _order(db, users, "cancelled")
        assert _bayar(anon).status_code == 200
        db.notifications.update_many({}, {"$set": {"read": True}})   # staf sudah membaca kabar pertama
        assert _bayar(anon).status_code == 200
        assert _bayar(anon).status_code == 200
        assert db.logs.count_documents({"action": "pembayaran_terlambat"}) == 1
        assert db.notifications.count_documents({"read": False}) == 0   # kabar tidak dimunculkan lagi
        assert db.orders.find_one({"code": ORDER_CODE})["needs_refund"] is True

    def test_nominal_tidak_cocok_tidak_menandai_refund(self, db, users, xendit, anon):
        _order(db, users, "cancelled")
        assert _bayar(anon, amount=1000).status_code == 200
        order = db.orders.find_one({"code": ORDER_CODE})
        assert order.get("needs_refund") is None and order["payment_issue"] == "mismatch"