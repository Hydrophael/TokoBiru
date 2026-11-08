"""Tes untuk Lupa password: kode email, sekali pakai, kedaluwarsa, batas tebakan, dan sesi"""
import os
import re
import sys
from datetime import timedelta

import mongomock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as tb  # noqa: E402

OLD = "rahasia123"
NEW = "barubaru456"
EMAIL = "budi@t.test"


@pytest.fixture
def env(monkeypatch):
    """(db, sent): database kosong dengan satu pelanggan `budi`; email ditampung di `sent`, bukan dikirim."""
    database = mongomock.MongoClient().tokobiru
    monkeypatch.setattr(tb, "_db", database)
    monkeypatch.setattr(tb, "_last_sweep", None)
    monkeypatch.setattr(tb, "EMAIL_ENABLED", True)
    sent = []
    monkeypatch.setattr(tb, "send_email", lambda to, subject, body, html=None: sent.append((to, body, html)))
    database.users.insert_one(tb.new_user_doc(
        {"name": "Budi", "username": "budi", "email": EMAIL, "password": OLD}, "user"))
    return database, sent


def anon():
    client = tb.app.test_client()
    client.csrf = client.get("/api/auth/me").get_json()["csrf"]
    return client


def post(client, path, body):
    return client.post("/api/auth/" + path, json=body, headers={"X-CSRF-Token": client.csrf})


def login(password=OLD, username="budi"):
    client = anon()
    res = post(client, "login", {"identifier": username, "password": password})
    client.csrf = res.get_json().get("csrf", client.csrf)
    client.login_status = res.status_code
    return client


def request_code(client, sent, email=EMAIL):
    assert post(client, "forgot", {"email": email}).status_code == 200
    return re.search(r"\b(\d{6})\b", sent[-1][1]).group(1)


def reset(client, code, new=NEW, email=EMAIL):
    return post(client, "reset", {"email": email, "code": code, "new_password": new})


def wrong_code(real):
    return "000000" if real != "000000" else "111111"


def user_doc(db):
    return db.users.find_one({"username": "budi"})


# --- berhasil ---------------------------------------------------------------
def test_alur_lengkap(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    assert reset(client, code).status_code == 200
    assert login(OLD).login_status == 401               # password lama tidak berlaku lagi
    assert login(NEW).login_status == 200
    assert db.logs.find_one({"action": "password_reset"})["actor"] == "budi"


def test_email_tidak_peka_huruf_besar(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent, email="Budi@T.Test")
    assert reset(client, code, email="BUDI@t.test").status_code == 200


def test_reset_tidak_membuat_sesi_login(env):
    db, sent = env
    client = anon()
    reset(client, request_code(client, sent))
    assert client.get("/api/orders").status_code == 401


def test_kode_hanya_sekali_pakai(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    assert reset(client, code).status_code == 200
    assert reset(client, code, new="lainlain789").status_code == 422
    assert login(NEW).login_status == 200


def test_berhasil_membersihkan_semua_bekas_reset(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    reset(client, wrong_code(code))                      # satu tebakan salah meninggalkan penghitung
    assert user_doc(db)["reset_failed"] == 1
    assert reset(client, code).status_code == 200
    user = user_doc(db)
    for key in ("reset_code_hash", "reset_expires", "reset_sent_at", "reset_failed", "reset_locked_until"):
        assert key not in user


# --- ditolak ----------------------------------------------------------------
def test_kode_salah_ditolak_dan_password_tetap(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    res = reset(client, wrong_code(code))
    assert res.status_code == 422 and "code" in res.get_json()["fields"]
    assert login(OLD).login_status == 200
    assert db.logs.find_one({"action": "reset_gagal"})["actor"] == "budi"


def test_kode_kedaluwarsa_ditolak(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    db.users.update_one({"username": "budi"}, {"$set": {"reset_expires": tb.utcnow() - timedelta(minutes=1)}})
    assert reset(client, code).status_code == 422
    assert login(OLD).login_status == 200


def test_tanpa_permintaan_kode_ditolak(env):
    db, sent = env
    assert reset(anon(), "123456").status_code == 422


@pytest.mark.parametrize("bad", ["12345", "1234567", "12ab56", "", "      "])
def test_format_kode_salah_ditolak_tanpa_menghitung(env, bad):
    db, sent = env
    client = anon()
    request_code(client, sent)
    assert reset(client, bad).status_code == 422
    assert "reset_failed" not in user_doc(db)


@pytest.mark.parametrize("weak", ["pendek1", "hanyahuruf", "1234567890", ""])
def test_password_lemah_ditolak_dan_kode_tetap_bisa_dipakai(env, weak):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    assert reset(client, code, new=weak).status_code == 422
    assert "reset_failed" not in user_doc(db)            # validasi gagal tidak memakai jatah tebakan
    assert reset(client, code).status_code == 200


def test_tebakan_tanpa_kode_aktif_tidak_dihitung(env):
    """Penyerang tidak bisa mengunci reset akun orang lain sebelum pemiliknya meminta kode."""
    db, sent = env
    client = anon()
    for _ in range(tb.MAX_RESET_ATTEMPTS + 2):
        assert reset(client, "123456").status_code == 422
    assert "reset_failed" not in user_doc(db) and "reset_locked_until" not in user_doc(db)


def test_tebakan_pada_kode_kedaluwarsa_tidak_dihitung(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    db.users.update_one({"username": "budi"}, {"$set": {"reset_expires": tb.utcnow() - timedelta(minutes=1)}})
    reset(client, wrong_code(code))
    assert "reset_failed" not in user_doc(db)


def test_akun_nonaktif_tidak_dikirimi_kode_dan_tidak_bisa_reset(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    db.users.update_one({"username": "budi"}, {"$set": {"active": False}})
    assert reset(client, code).status_code == 422
    sent.clear()
    db.users.update_one({"username": "budi"}, {"$unset": {"reset_sent_at": ""}})
    assert post(client, "forgot", {"email": EMAIL}).status_code == 200
    assert sent == []


# --- minta kode ---------------------------------------------------------------
def test_jawaban_forgot_sama_untuk_email_terdaftar_atau_tidak(env):
    db, sent = env
    client = anon()
    known = post(client, "forgot", {"email": EMAIL})
    unknown = post(client, "forgot", {"email": "tidak.ada@t.test"})
    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert len(sent) == 1 and sent[0][0] == EMAIL


def test_jeda_antar_permintaan_kode(env):
    db, sent = env
    client = anon()
    request_code(client, sent)
    post(client, "forgot", {"email": EMAIL})
    assert len(sent) == 1
    db.users.update_one({"username": "budi"}, {"$set": {"reset_sent_at": tb.utcnow() - timedelta(minutes=3)}})
    post(client, "forgot", {"email": EMAIL})
    assert len(sent) == 2


def test_kode_baru_membatalkan_kode_lama(env):
    db, sent = env
    client = anon()
    old_code = request_code(client, sent)
    db.users.update_one({"username": "budi"}, {"$set": {"reset_sent_at": tb.utcnow() - timedelta(minutes=3)}})
    new_code = request_code(client, sent)
    if old_code != new_code:
        assert reset(client, old_code).status_code == 422
    assert reset(client, new_code).status_code == 200


def test_gagal_kirim_email_membatalkan_kode_dan_boleh_coba_lagi(env, monkeypatch):
    db, sent = env

    def boom(*args, **kwargs):
        raise OSError("smtp mati")
    monkeypatch.setattr(tb, "send_email", boom)
    client = anon()
    assert post(client, "forgot", {"email": EMAIL}).status_code == 200
    user = user_doc(db)
    assert "reset_code_hash" not in user and "reset_sent_at" not in user
    monkeypatch.setattr(tb, "send_email", lambda to, subject, body, html=None: sent.append((to, body, html)))
    request_code(client, sent)                           # langsung bisa meminta lagi, tanpa menunggu jeda


def test_nonaktif_bila_smtp_belum_diatur(env, monkeypatch):
    monkeypatch.setattr(tb, "EMAIL_ENABLED", False)
    client = anon()
    assert post(client, "forgot", {"email": EMAIL}).status_code == 503
    assert reset(client, "123456").status_code == 503
    assert client.get("/api/auth/me").get_json()["reset_enabled"] is False


# --- batas tebakan -------------------------------------------------------------
def test_tebakan_salah_dibatasi_lalu_kode_benar_pun_ditolak(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    bad = wrong_code(code)
    for _ in range(tb.MAX_RESET_ATTEMPTS - 1):
        assert reset(client, bad).status_code == 422
    assert reset(client, bad).status_code == 429         # tebakan terakhir memasang kunci
    assert reset(client, code).status_code == 429        # kode benar pun ditolak selama terkunci
    assert login(OLD).login_status == 200


def test_kunci_reset_tidak_mengunci_login(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    for _ in range(tb.MAX_RESET_ATTEMPTS):
        reset(client, wrong_code(code))
    assert "locked_until" not in user_doc(db) or user_doc(db)["locked_until"] is None
    assert login(OLD).login_status == 200                # pemilik akun tetap bisa masuk


def test_kunci_reset_berakhir(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    for _ in range(tb.MAX_RESET_ATTEMPTS):
        reset(client, wrong_code(code))
    assert reset(client, code).status_code == 429
    db.users.update_one({"username": "budi"}, {"$set": {"reset_locked_until": tb.utcnow() - timedelta(seconds=1)}})
    assert reset(client, code).status_code == 200


def test_penghitung_tidak_dihapus_oleh_kode_baru(env):
    """Meminta kode baru tidak memberi jatah tebakan baru (kalau tidak, batasnya bisa dilewati)."""
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    for _ in range(tb.MAX_RESET_ATTEMPTS - 1):
        reset(client, wrong_code(code))
    db.users.update_one({"username": "budi"}, {"$set": {"reset_sent_at": tb.utcnow() - timedelta(minutes=3)}})
    new_code = request_code(client, sent)
    assert user_doc(db)["reset_failed"] == tb.MAX_RESET_ATTEMPTS - 1
    assert reset(client, wrong_code(new_code)).status_code == 429


def test_gagal_kirim_email_tidak_menghapus_kunci(env, monkeypatch):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    for _ in range(tb.MAX_RESET_ATTEMPTS):
        reset(client, wrong_code(code))
    locked_until = user_doc(db)["reset_locked_until"]
    db.users.update_one({"username": "budi"}, {"$set": {"reset_sent_at": tb.utcnow() - timedelta(minutes=3)}})

    def boom(*args, **kwargs):
        raise OSError("smtp mati")
    monkeypatch.setattr(tb, "send_email", boom)
    post(client, "forgot", {"email": EMAIL})
    assert user_doc(db)["reset_locked_until"] == locked_until


def test_penghitung_menggantung_di_atas_batas_tetap_terkunci(env):
    """Bila request macet sebelum kunci sempat dipasang, tebakan berikutnya tidak dicocokkan dan kunci dipasang."""
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    db.users.update_one({"username": "budi"}, {"$set": {"reset_failed": tb.MAX_RESET_ATTEMPTS}})
    assert reset(client, code).status_code == 429        # kode benar pun tidak dicocokkan
    assert user_doc(db)["reset_locked_until"] > tb.utcnow()
    assert login(OLD).login_status == 200


# --- hubungan dengan kunci login ------------------------------------------------
def test_akun_terkunci_karena_login_gagal_tetap_bisa_direset(env):
    db, sent = env
    client = anon()
    for _ in range(tb.MAX_FAILED_LOGIN):
        post(client, "login", {"identifier": "budi", "password": "salah12345"})
    assert login(OLD).login_status == 429                # memang terkunci
    code = request_code(client, sent)
    assert reset(client, code).status_code == 200
    assert login(NEW).login_status == 200                # reset berhasil sekaligus membuka kunci login


def test_tebakan_reset_salah_tidak_menambah_hitungan_gagal_login(env):
    db, sent = env
    client = anon()
    code = request_code(client, sent)
    reset(client, wrong_code(code))
    assert user_doc(db).get("failed", 0) == 0


# --- sesi dan kebocoran data ----------------------------------------------------
def test_sesi_di_semua_perangkat_dicabut(env):
    db, sent = env
    laptop, hp = login(), login()
    assert laptop.get("/api/orders").status_code == 200
    client = anon()
    assert reset(client, request_code(client, sent)).status_code == 200
    assert laptop.get("/api/orders").status_code == 401
    assert hp.get("/api/orders").status_code == 401
    body = hp.get("/api/auth/me")
    assert body.status_code == 200 and body.get_json()["user"] is None


def test_data_reset_tidak_bocor_ke_daftar_pengguna(env):
    db, sent = env
    db.users.insert_one(tb.new_user_doc(
        {"name": "Bos", "username": "bos", "email": "bos@t.test", "password": OLD}, "master"))
    client = anon()
    code = request_code(client, sent)
    reset(client, wrong_code(code))                      # meninggalkan reset_failed di dokumen
    bos = login(username="bos")
    users = bos.get("/api/users").get_json()["users"]
    hidden = ("reset_code_hash", "reset_expires", "reset_sent_at", "reset_failed", "reset_locked_until")
    assert users and all(key not in u for u in users for key in hidden)
    me = login().get("/api/auth/me").get_json()["user"]
    assert all(key not in me for key in hidden)


# --- isi email dan jawaban untuk frontend ---------------------------------------
def test_email_berisi_teks_dan_html_dengan_kode_yang_sama(env):
    db, sent = env
    request_code(anon(), sent)
    to, text, html = sent[0]
    code = re.search(r"\b(\d{6})\b", text).group(1)
    assert to == EMAIL and "Budi" in text
    assert html and code in html and "Budi" in html and "<html" in html


def test_nama_di_email_html_di_escape():
    html = tb.reset_email_html('<script>alert(1)</script> & "x"', "123456")
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;" in html


def test_send_email_membuat_multipart_teks_dan_html(monkeypatch):
    captured = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            captured.append(message)

    monkeypatch.setattr(tb.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(tb, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(tb, "SMTP_FROM", "TokoBiru <t@t.test>")
    monkeypatch.setattr(tb, "SMTP_USER", "")
    tb.send_email(EMAIL, "Tes", "isi teks 123456", html="<p>isi html 123456</p>")
    message = captured[0]
    assert message.is_multipart()
    assert "123456" in message.get_body(("plain",)).get_content()
    assert "123456" in message.get_body(("html",)).get_content()


def test_send_email_tanpa_html_tetap_teks_biasa(monkeypatch):
    captured = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def send_message(self, message):
            captured.append(message)

    monkeypatch.setattr(tb.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(tb, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(tb, "SMTP_FROM", "t@t.test")
    monkeypatch.setattr(tb, "SMTP_USER", "")
    tb.send_email(EMAIL, "Tes", "hanya teks")
    assert not captured[0].is_multipart()


def test_forgot_memberi_jeda_dan_masa_berlaku_yang_sama_untuk_semua_email(env):
    db, sent = env
    client = anon()
    known = post(client, "forgot", {"email": EMAIL}).get_json()
    unknown = post(client, "forgot", {"email": "tidak.ada@t.test"}).get_json()
    assert known == unknown
    assert known["retry_after"] == tb.RESET_COOLDOWN_SECONDS
    assert known["expires_minutes"] == tb.RESET_CODE_MINUTES