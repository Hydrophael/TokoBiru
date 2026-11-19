"""Tes get_db(): indeks yang gagal tidak menjatuhkan aplikasi, galat jaringan tidak disimpan. Simpan di tests/unit/."""
import mongomock
import pytest
from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

from tokobiru.core import connection


@pytest.fixture()
def fresh_db(monkeypatch):
    """get_db() murni (bukan _db palsu dari conftest) dengan MongoClient diganti mongomock."""
    fake = mongomock.MongoClient()["tokobiru_conn"]
    monkeypatch.setattr(connection, "_db", None)
    monkeypatch.setattr(connection, "after_connect", None)
    monkeypatch.setattr(connection, "MongoClient", lambda *a, **k: {connection.mongo_db_name(): fake})
    return fake


def _break_create_index(monkeypatch, error, only=None):
    original = mongomock.collection.Collection.create_index

    def flaky(self, keys, **kwargs):
        if only is None or (self.name, keys[0][0]) == only:
            raise error
        return original(self, keys, **kwargs)
    monkeypatch.setattr(mongomock.collection.Collection, "create_index", flaky)


def test_satu_indeks_gagal_tidak_menjatuhkan_get_db(fresh_db, monkeypatch):
    _break_create_index(monkeypatch, OperationFailure("duplicate key"), only=("users", "username"))
    assert connection.get_db() is fresh_db
    assert connection._db is fresh_db
    assert "email_1" in fresh_db.users.index_information()      # indeks lain tetap dibuat
    assert connection.ensure_indexes(fresh_db) == ["users.username_1"]


def test_galat_jaringan_tidak_menyimpan_koneksi(fresh_db, monkeypatch):
    _break_create_index(monkeypatch, ServerSelectionTimeoutError("putus"))
    with pytest.raises(ServerSelectionTimeoutError):
        connection.get_db()
    assert connection._db is None                                # request berikutnya mencoba lagi


def test_index_setup_bisa_dimatikan(fresh_db, monkeypatch):
    monkeypatch.setattr(connection, "INDEX_SETUP_ON_CONNECT", False)
    monkeypatch.setattr(connection, "ensure_indexes", lambda db: pytest.fail("tidak boleh dipanggil"))
    assert connection.get_db() is fresh_db