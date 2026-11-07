"""Tes untuk ganti password: validasi, batas gagal, pencabutan sesi lain, dan regresi /auth/me."""
import os
import sys

import mongomock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as tb  # noqa: E402

OLD = "rahasia123"
NEW = "barubaru456"


@pytest.fixture
def db(monkeypatch):
    database = mongomock.MongoClient().tokobiru
    monkeypatch.setattr(tb, "_db", database)
    monkeypatch.setattr(tb, "_last_sweep", None)
    return database


def make_user(db, username, role="user"):
    db.users.insert_one(tb.new_user_doc({
        "name": username.title(), "username": username,
        "email": f"{username}@t.test", "password": OLD}, role))


def login(username, password=OLD):
    client = tb.app.test_client()
    csrf = client.get("/api/auth/me").get_json()["csrf"]
    res = client.post("/api/auth/login", json={"identifier": username, "password": password},
                      headers={"X-CSRF-Token": csrf})
    client.csrf = res.get_json().get("csrf", csrf)
    client.login_status = res.status_code
    return client


def change(client, current=OLD, new=NEW):
    return client.patch("/api/auth/password", json={"current_password": current, "new_password": new},
                        headers={"X-CSRF-Token": client.csrf})


# --- berhasil ---------------------------------------------------------------
def test_ganti_password_berhasil(db):
    make_user(db, "budi")
    budi = login("budi")
    assert change(budi).status_code == 200
    assert login("budi", OLD).login_status == 401       # password lama tidak berlaku lagi
    assert login("budi", NEW).login_status == 200
    assert db.logs.find_one({"action": "password_ubah"})["actor"] == "budi"


def test_berhasil_mereset_hitungan_gagal(db):
    make_user(db, "budi")
    budi = login("budi")
    change(budi, current="salah12345")
    change(budi, current="salah12345")
    assert db.users.find_one({"username": "budi"})["failed"] == 2
    assert change(budi).status_code == 200
    assert db.users.find_one({"username": "budi"})["failed"] == 0


# --- ditolak ----------------------------------------------------------------
def test_password_lama_salah_ditolak(db):
    make_user(db, "budi")
    budi = login("budi")
    res = change(budi, current="salah12345")
    assert res.status_code == 422 and "current_password" in res.get_json()["fields"]
    assert login("budi", OLD).login_status == 200       # password tidak berubah
    assert db.logs.find_one({"action": "password_gagal"})["actor"] == "budi"


@pytest.mark.parametrize("weak", ["pendek1", "hanyahuruf", "1234567890", ""])
def test_password_baru_lemah_ditolak(db, weak):
    make_user(db, "budi")
    res = change(login("budi"), new=weak)
    assert res.status_code == 422 and "new_password" in res.get_json()["fields"]
    assert login("budi", OLD).login_status == 200


def test_password_baru_harus_berbeda(db):
    make_user(db, "budi")
    res = change(login("budi"), new=OLD)
    assert res.status_code == 422 and "new_password" in res.get_json()["fields"]


def test_password_lama_wajib_diisi(db):
    make_user(db, "budi")
    budi = login("budi")
    res = budi.patch("/api/auth/password", json={"new_password": NEW}, headers={"X-CSRF-Token": budi.csrf})
    assert res.status_code == 422 and "current_password" in res.get_json()["fields"]


def test_wajib_login(db):
    anon = tb.app.test_client()
    anon.csrf = anon.get("/api/auth/me").get_json()["csrf"]
    assert change(anon).status_code == 401


# --- batas gagal ------------------------------------------------------------
def test_tebakan_password_lama_dibatasi(db):
    make_user(db, "budi")
    budi = login("budi")
    for _ in range(tb.MAX_FAILED_LOGIN):
        assert change(budi, current="salah12345").status_code == 422
    # akun terkunci: bahkan password lama yang benar ditolak, baik di sini maupun saat login
    assert change(budi).status_code == 429
    assert login("budi", OLD).login_status == 429
    assert login("budi", NEW).login_status == 429


# --- sesi ---------------------------------------------------------------------
def test_sesi_di_perangkat_lain_dicabut(db):
    make_user(db, "budi")
    laptop, hp = login("budi"), login("budi")
    assert hp.get("/api/orders").status_code == 200

    assert change(laptop).status_code == 200
    assert laptop.get("/api/orders").status_code == 200   # sesi yang dipakai tetap berlaku
    assert hp.get("/api/orders").status_code == 401       # sesi lain tidak berlaku lagi


def test_sesi_dicabut_tidak_membuat_auth_me_error(db):
    """Muat ulang halaman di perangkat yang sesinya dicabut: /auth/me harus membalas 'belum masuk',
    bukan 500 (sebelumnya csrf dibaca dari sesi yang baru saja dibersihkan)."""
    make_user(db, "budi")
    laptop, hp = login("budi"), login("budi")
    change(laptop)
    res = hp.get("/api/auth/me")
    body = res.get_json()
    assert res.status_code == 200 and body["user"] is None and body["csrf"]


def test_login_ulang_setelah_dicabut_berhasil(db):
    make_user(db, "budi")
    laptop, hp = login("budi"), login("budi")
    change(laptop)
    assert hp.get("/api/orders").status_code == 401
    # klien mengambil csrf baru dari /auth/me lalu masuk dengan password baru
    csrf = hp.get("/api/auth/me").get_json()["csrf"]
    res = hp.post("/api/auth/login", json={"identifier": "budi", "password": NEW},
                  headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200
    hp.csrf = res.get_json()["csrf"]
    assert hp.get("/api/orders").status_code == 200


def test_akun_nonaktif_tidak_membuat_auth_me_error(db):
    make_user(db, "budi")
    budi = login("budi")
    db.users.update_one({"username": "budi"}, {"$set": {"active": False}})
    res = budi.get("/api/auth/me")
    assert res.status_code == 200 and res.get_json()["user"] is None


def test_versi_sesi_tidak_bocor_ke_daftar_pengguna(db):
    make_user(db, "bos", "master")
    make_user(db, "budi")
    change(login("budi"))
    bos = login("bos")
    users = bos.get("/api/users").get_json()["users"]
    assert users and all("session_version" not in u for u in users)