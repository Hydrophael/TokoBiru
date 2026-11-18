"""TokoBiru - hash dan pemeriksaan password.

Dipisah supaya tes cukup mem-patch satu tempat (lihat tests/conftest.py). Pemanggil harus memakai
`passwords.hash_password(...)`, bukan `from tokobiru.core.passwords import hash_password`, supaya patch berlaku.
"""
import secrets

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    return generate_password_hash(password)


def check_password(stored_hash, password):
    return check_password_hash(stored_hash, password)


# Dipakai saat akun tidak ada: pemeriksaan tetap berjalan, jadi waktu respons tidak membocorkan username
DUMMY_HASH = generate_password_hash(secrets.token_hex(8))