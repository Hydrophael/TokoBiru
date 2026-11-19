"""TokoBiru - validasi dan sanitasi input: regex, pesan galat, Form, decode foto, dan pembaca body JSON.

"""
import base64
import re
import unicodedata

from bson import ObjectId
from flask import request

from tokobiru.core.config import PASSWORD_MAX_LEN, PASSWORD_MIN_LEN
from tokobiru.errors import ApiError

TAG_RE = re.compile(r"<[^>]*>")
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
BLANK_LINES_RE = re.compile(r"\n{3,}")
USERNAME_RE = re.compile(r"[a-z0-9_]{3,20}")
EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}")
PERSON_RE = re.compile(r"[A-Za-zÀ-ÿ0-9 .,'\-]+")
OID_RE = re.compile(r"[0-9a-fA-F]{24}")
LETTER_RE = re.compile(r"[A-Za-z]")
DIGIT_RE = re.compile(r"\d")
INT_TEXT_RE = re.compile(r"-?\d{1,12}")
PHONE_RE = re.compile(r"\+?\d{8,15}")
PHONE_ERROR = "Isi nomor HP yang benar, contoh 081234567890"

NAME_ERROR = "Nama hanya boleh huruf, angka, spasi, titik, koma, apostrof, strip"
USERNAME_ERROR = "Username 3-20 karakter: huruf kecil, angka, underscore"
EMAIL_ERROR = "Format email tidak valid"
RESET_CODE_RE = re.compile(r"\d{6}")
RESET_CODE_ERROR = "Kode terdiri dari 6 angka"
RESET_FAILED_ERROR = "Kode salah atau sudah kedaluwarsa. Minta kode baru bila perlu."


def sanitize(value, multiline=False):
    value = unicodedata.normalize("NFKC", value)
    value = CTRL_RE.sub("", value)
    value = TAG_RE.sub("", value)
    value = value.replace("<", "").replace(">", "")
    if multiline:
        value = value.replace("\r", "")
        value = "\n".join(" ".join(line.split()) for line in value.split("\n"))
        value = BLANK_LINES_RE.sub("\n\n", value)
    else:
        value = " ".join(value.split())
    return value.strip()


def parse_int(raw):
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and INT_TEXT_RE.fullmatch(raw.strip()):
        return int(raw.strip())
    return None


def is_strong_password(password):
    return (
        len(password) >= PASSWORD_MIN_LEN
        and bool(LETTER_RE.search(password))
        and bool(DIGIT_RE.search(password))
    )


IMAGE_MAX_CHARS = 300_000
PROOF_IMAGE_MAX_CHARS = 700_000   # bukti transfer: angka kecil di struk butuh resolusi lebih tinggi daripada foto produk
IMAGE_RE = re.compile(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})")


def decode_image(raw, max_chars=IMAGE_MAX_CHARS):
    if len(raw) > max_chars:
        raise ValueError("Foto terlalu besar. Pilih foto lain.")
    match = IMAGE_RE.fullmatch(raw)
    if not match:
        raise ValueError("Foto tidak valid. Gunakan JPG, PNG, atau WebP.")
    mime, payload = match.groups()
    try:
        data = base64.b64decode(payload, validate=True)
    except ValueError:
        raise ValueError("Foto tidak valid. Gunakan JPG, PNG, atau WebP.") from None
    signature_ok = (
        (mime == "image/jpeg" and data[:3] == b"\xff\xd8\xff")
        or (mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n")
        or (mime == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP")
    )
    if not signature_ok:
        raise ValueError("Foto tidak valid. Gunakan JPG, PNG, atau WebP.")
    return data, mime


class Form:
    def __init__(self, data):
        self.data = data if isinstance(data, dict) else {}
        self.errors = {}
        self.out = {}

    def _empty(self, name, label, required):
        if required:
            self.errors[name] = f"{label} wajib diisi"
        else:
            self.out[name] = ""

    def text(self, name, label, min_len=0, max_len=100, required=True,
             multiline=False, regex=None, regex_msg=None, lower=False):
        raw = self.data.get(name)
        if raw is None or raw == "":
            return self._empty(name, label, required)
        if not isinstance(raw, str):
            self.errors[name] = f"{label} tidak valid"
            return
        value = sanitize(raw, multiline)
        if lower:
            value = value.lower()
        if not value:
            return self._empty(name, label, required)
        if len(value) < min_len:
            self.errors[name] = f"{label} minimal {min_len} karakter"
        elif len(value) > max_len:
            self.errors[name] = f"{label} maksimal {max_len} karakter"
        elif regex and not regex.fullmatch(value):
            self.errors[name] = regex_msg or f"Format {label} tidak valid"
        else:
            self.out[name] = value

    def password(self, name="password", label="Password", enforce_policy=True):
        raw = self.data.get(name)
        if not isinstance(raw, str) or raw == "":
            self.errors[name] = f"{label} wajib diisi"
            return
        if len(raw) > PASSWORD_MAX_LEN:
            self.errors[name] = f"{label} maksimal {PASSWORD_MAX_LEN} karakter"
        elif enforce_policy and not is_strong_password(raw):
            self.errors[name] = (
                f"{label} minimal {PASSWORD_MIN_LEN} karakter dan mengandung huruf serta angka"
            )
        else:
            self.out[name] = raw

    def integer(self, name, label, lo, hi):
        raw = self.data.get(name)
        if raw is None or raw == "" or isinstance(raw, bool):
            self.errors[name] = f"{label} wajib diisi"
            return
        number = parse_int(raw)
        if number is None:
            self.errors[name] = f"{label} harus berupa bilangan bulat"
        elif number < lo or number > hi:
            self.errors[name] = f"{label} harus antara {lo:,} dan {hi:,}".replace(",", ".")
        else:
            self.out[name] = number

    def image(self, name="image", label="Foto", max_chars=IMAGE_MAX_CHARS):
        if name not in self.data:
            return
        raw = self.data[name]
        if raw is None or raw == "":
            self.out[name] = None
            return
        if not isinstance(raw, str):
            self.errors[name] = f"{label} tidak valid"
            return
        try:
            self.out[name] = decode_image(raw, max_chars)
        except ValueError as exc:
            self.errors[name] = str(exc)

    def choice(self, name, label, options):
        raw = self.data.get(name)
        if not isinstance(raw, str) or raw not in options:
            self.errors[name] = f"{label} tidak valid"
        else:
            self.out[name] = raw

    def done(self):
        if self.errors:
            raise ApiError("Periksa kembali isian Anda", 422, self.errors)
        return self.out


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Data yang dikirim tidak terbaca. Muat ulang halaman lalu coba lagi.", 400)
    return data


def object_id(value, label="ID"):
    if not isinstance(value, str) or not OID_RE.fullmatch(value):
        raise ApiError(f"{label} tidak valid", 400)
    return ObjectId(value)