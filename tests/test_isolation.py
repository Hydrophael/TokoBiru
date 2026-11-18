"""Penjaga: tes tidak boleh pernah terhubung ke MongoDB sungguhan."""
import app


def test_koneksi_asli_diblokir_saat_tes():
    assert app.mongo_uri() == "mongodb://127.0.0.1:1"
