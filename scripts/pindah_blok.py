"""Pemindah blok kode dari app.py ke modul di paket tokobiru/, satu tugas per langkah refactor.

Aman dijalankan ulang. Sebelum dan sesudah memindah, semua nama dan nilai di modul `app`
dibandingkan; bila ada yang berbeda (selain yang memang sengaja hilang), semua berkas
dikembalikan seperti semula.

Jalankan dari akar proyek:  python scripts/pindah_blok.py <nama tugas>
"""
import ast
import builtins
import json
import os
import shutil
import subprocess
import sys

ROOT = os.getcwd()
APP = os.path.join(ROOT, "app.py")
JANGKAR = "from tokobiru.util import"   # impor ulang disisipkan setelah baris ini
JANGKAR_UTAMA = '\nif __name__ == "__main__":'

# Tiap tugas:
#   modul        nama berkas tujuan di tokobiru/
#   kepala       isi awal berkas tujuan (docstring dan impor)
#   potongan     [(penanda awal, penanda akhir)]: dari awal sampai sebelum akhir
#   ganti        (opsional) [(lama, baru)] yang diterapkan pada blok yang dipindah
#   boleh_hilang (opsional) nama yang sengaja tidak ada lagi di modul app
#   impor_ekstra (opsional) baris impor tambahan di app.py
#   sebelum_main (opsional) baris yang disisipkan di app.py sebelum `if __name__ == "__main__"`
#   setelah_baris (opsional) (teks acuan, baris baru): baris baru disisipkan tepat setelah teks acuan di app.py
#   tambah_modul (opsional) kode yang ditambahkan di akhir modul tujuan, di luar blok yang dipindah
#   berkas_lain  (opsional) {berkas: [(lama, baru)]} untuk menyesuaikan berkas lain, mis. tes
TUGAS = {
    "serializers": {
        "modul": "serializers",
        "kepala": (
            '"""TokoBiru - mengubah dokumen MongoDB menjadi JSON untuk klien (menyembunyikan field internal).\n\n'
            "Nama-nama di sini masih diimpor ulang oleh app.py supaya kode dan tes lama tetap jalan.\n"
            '"""\n'
            "from datetime import datetime\n\n"
            "from bson import ObjectId\n\n"
            "from tokobiru.config import STAFF_ROLES, XENDIT_SIMULATE_SCAN\n\n\n"
        ),
        "potongan": [("HIDDEN_FIELDS = (", "def public_user("), ("def address_json(", "def address_form(")],
    },
    "validasi": {
        "modul": "validation",
        "kepala": (
            '"""TokoBiru - validasi dan sanitasi input: regex, pesan galat, Form, decode foto, dan pembaca body JSON.\n\n'
            "Nama-nama di sini masih diimpor ulang oleh app.py supaya kode dan tes lama tetap jalan.\n"
            '"""\n'
            "import base64\n"
            "import re\n"
            "import unicodedata\n\n"
            "from bson import ObjectId\n"
            "from flask import request\n\n"
            "from tokobiru.config import PASSWORD_MAX_LEN, PASSWORD_MIN_LEN\n"
            "from tokobiru.errors import ApiError\n\n\n"
        ),
        "potongan": [("TAG_RE = re.compile(", "def public_user(")],
    },
    "koneksi": {
        "modul": "koneksi",
        "kepala": (
            '"""TokoBiru - koneksi MongoDB: alamat, nama database, migrasi koleksi lama, dan indeks.\n\n'
            "get_db() menyimpan koneksi di _db. Tes memasang database tiruan dengan mengganti tokobiru.koneksi._db\n"
            "(lihat use_db di tests/conftest.py). Nama-nama selain _db masih diimpor ulang oleh app.py.\n"
            '"""\n'
            "import logging\n\n"
            "from pymongo import ASCENDING, DESCENDING, MongoClient\n"
            "from pymongo.errors import OperationFailure, PyMongoError\n\n"
            "from tokobiru.config import (IS_VERCEL, LEGACY_PRODUCT_COLLECTION, LOG_RETENTION_DAYS,\n"
            "                             PRODUCT_COLLECTION, PROOF_RETENTION_DAYS, _env_str)\n\n"
            'log = logging.getLogger("app")   # logger yang sama dengan app.logger\n\n'
            "# Diisi app.py (bootstrap): dipanggil sekali setelah koneksi pertama berhasil\n"
            "sesudah_terhubung = None\n\n"
        ),
        "potongan": [("_db = None", "@app.errorhandler(ApiError)")],
        "ganti": [("app.logger.", "log."),
                  ("    bootstrap(db)\n", "    if sesudah_terhubung:\n        sesudah_terhubung(db)\n")],
        "boleh_hilang": ["_db"],
        "impor_ekstra": "from tokobiru import koneksi  # noqa: E402\n",
        "sebelum_main": "koneksi.sesudah_terhubung = bootstrap\n",
        "berkas_lain": {
            "tests/conftest.py": [
                ("from tokobiru import passwords  # noqa: E402\n",
                 "from tokobiru import koneksi, passwords  # noqa: E402\n"),
                ('monkeypatch.setattr(tokobiru, "_db", database)',
                 'monkeypatch.setattr(koneksi, "_db", database)'),
            ],
        },
    },
    "keamanan": {
        "modul": "keamanan",
        "kepala": (
            '"""TokoBiru - keamanan: header, IP klien, pembatasan percobaan, sesi dan peran, CSRF, dan log audit.\n\n'
            "Pemeriksaan sebelum/sesudah request dipasang lewat pasang(app). Nama-nama di sini masih diimpor\n"
            'ulang oleh app.py supaya kode dan tes lama tetap jalan.\n"""\n'
            "import secrets\n"
            "from datetime import timedelta\n"
            "from functools import wraps\n\n"
            "from bson import ObjectId\n"
            "from flask import g, has_request_context, request, session\n"
            "from pymongo import ReturnDocument\n"
            "from pymongo.errors import DuplicateKeyError, PyMongoError\n\n"
            "from tokobiru.config import (IS_VERCEL, LOCK_MINUTES, MAX_FAILED_LOGIN, MAX_JSON_BYTES, PRODUCT_WRITE_RE,\n"
            "                             PROFILE_WRITE_RE, PROOF_WRITE_RE, ROLES)\n"
            "from tokobiru.errors import ApiError\n"
            "from tokobiru.koneksi import get_db\n"
            "from tokobiru.util import utcnow\n"
            "from tokobiru.validation import OID_RE, sanitize\n\n\n"
        ),
        "potongan": [("SAFE_METHODS = (", "# --- Notifikasi push (Web Push)")],
        "ganti": [("@app.before_request\n", ""), ("@app.after_request\n", "")],
        "tambah_modul": (
            "def pasang(app):\n"
            '    """Daftarkan pemeriksaan sebelum dan sesudah tiap request ke aplikasi Flask."""\n'
            "    app.before_request(guard)\n"
            "    app.after_request(secure_headers)\n"
        ),
        "impor_ekstra": "from tokobiru import keamanan  # noqa: E402\n",
        "setelah_baris": ("koneksi.sesudah_terhubung = bootstrap\n", "keamanan.pasang(app)\n"),
    },
}


def nama_didefinisikan(blok):
    """Nama tingkat atas yang dibuat blok (fungsi, kelas, konstanta), sesuai urutan muncul."""
    hasil = []
    for node in ast.parse(blok).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            hasil.append(node.name)
        elif isinstance(node, ast.Assign):
            hasil += [t.id for t in node.targets if isinstance(t, ast.Name)]
    return hasil


def nama_bebas(kode):
    """Nama yang dipakai tapi tidak didefinisikan atau diimpor di berkas itu (tanda impor yang kurang)."""
    pohon = ast.parse(kode)
    ada = set(dir(builtins))
    for n in ast.walk(pohon):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            ada.add(n.name)
        elif isinstance(n, ast.arg):
            ada.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            ada.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            ada.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            ada.add(n.name)
    return sorted({n.id for n in ast.walk(pohon) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - ada)


def potong(teks, tugas):
    """Kembalikan (app.py baru, isi modul baru, daftar nama yang dipindah)."""
    rentang = []
    for awal_teks, akhir_teks in tugas["potongan"]:
        awal = teks.index("\n" + awal_teks) + 1
        akhir = teks.index("\n" + akhir_teks, awal) + 1
        rentang.append((awal, akhir))

    blok = "\n\n".join(teks[a:b].strip("\n") + "\n" for a, b in rentang)
    for lama, baru in tugas.get("ganti", []):
        if lama not in blok:
            raise ValueError(f"Teks yang mau diganti tidak ditemukan di blok: {lama!r}")
        blok = blok.replace(lama, baru)
    hilang = set(tugas.get("boleh_hilang", []))
    nama = [n for n in nama_didefinisikan(blok) if n not in hilang]

    sisa = teks
    for awal, akhir in sorted(rentang, reverse=True):
        sisa = sisa[:awal] + sisa[akhir:].lstrip("\n")
    kait = sisa.index(JANGKAR)
    ujung = sisa.index("\n", kait) + 1
    daftar = ",\n    ".join(nama)
    impor = (f"from tokobiru.{tugas['modul']} import (  # noqa: F401,E402\n    {daftar},\n)\n"
             + tugas.get("impor_ekstra", ""))
    sisa = sisa[:ujung] + impor + sisa[ujung:]
    if tugas.get("sebelum_main"):
        titik = sisa.index(JANGKAR_UTAMA)
        sisa = sisa[:titik].rstrip("\n") + "\n\n\n" + tugas["sebelum_main"] + "\n" + sisa[titik:]
    if tugas.get("setelah_baris"):
        acuan, baris_baru = tugas["setelah_baris"]
        if acuan not in sisa:
            raise ValueError(f"Baris acuan tidak ditemukan di app.py: {acuan.strip()!r} (langkah sebelumnya sudah dijalankan?)")
        titik = sisa.index(acuan) + len(acuan)
        sisa = sisa[:titik] + baris_baru + sisa[titik:]
    while "\n\n\n\n" in sisa:
        sisa = sisa.replace("\n\n\n\n", "\n\n\n")
    isi = tugas["kepala"] + blok
    if tugas.get("tambah_modul"):
        isi += "\n\n" + tugas["tambah_modul"]
    return sisa, isi, nama


SNAPSHOT = r"""
import json, os, sys, types
sys.path.insert(0, os.getcwd())
import app

ACAK = {"DUMMY_HASH"}   # hash dengan garam acak: berbeda tiap proses


def canon(value):
    if isinstance(value, types.ModuleType):
        return "<module>"
    if callable(value):
        return "<callable>"
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))}
    if isinstance(value, (set, frozenset)):
        return sorted(repr(canon(v)) for v in value)
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    return repr(value)


hasil = {}
for nama in dir(app):
    if nama.startswith("__"):
        continue
    hasil[nama] = "<acak>" if nama in ACAK else canon(getattr(app, nama))
print("@@" + json.dumps(hasil, sort_keys=True, default=repr))
"""


def snapshot():
    hasil = subprocess.run([sys.executable, "-c", SNAPSHOT], cwd=ROOT, capture_output=True, text=True)
    for baris in hasil.stdout.splitlines():
        if baris.startswith("@@"):
            return json.loads(baris[2:])
    sys.exit("Gagal membaca app.py:\n" + hasil.stderr[-1500:])


def baca(path):
    with open(path, encoding="utf-8", newline="") as fh:
        mentah = fh.read()
    return mentah.replace("\r\n", "\n"), "\r\n" if "\r\n" in mentah else "\n"


def tulis(path, teks, eol):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(teks.replace("\n", eol))


def main(argv):
    if len(argv) != 1 or argv[0] not in TUGAS:
        sys.exit("Pakai: python scripts/pindah_blok.py <" + "|".join(TUGAS) + ">")
    tugas = TUGAS[argv[0]]
    tujuan = os.path.join(ROOT, "tokobiru", tugas["modul"] + ".py")
    if os.path.exists(tujuan):
        print(f"tokobiru/{tugas['modul']}.py sudah ada; tidak ada yang dikerjakan.")
        return

    teks_app, eol_app = baca(APP)
    try:
        baru, isi, nama = potong(teks_app, tugas)
    except ValueError as err:
        sys.exit(f"{err}\nTidak ada yang diubah.")
    kurang = nama_bebas(isi)
    if kurang:
        sys.exit("Modul baru memakai nama yang belum diimpor: " + ", ".join(kurang) + "\nTidak ada yang diubah.")

    # berkas lain (mis. tests/conftest.py): semua teks yang diganti harus ada, sebelum apa pun ditulis
    lain = {}
    for berkas, pasangan in tugas.get("berkas_lain", {}).items():
        path = os.path.join(ROOT, *berkas.split("/"))
        if not os.path.exists(path):
            sys.exit(f"{berkas} tidak ditemukan. Tidak ada yang diubah.")
        teks, eol = baca(path)
        for lama, ganti in pasangan:
            if lama not in teks:
                sys.exit(f"{berkas}: teks ini tidak ditemukan: {lama.strip()!r}\nTidak ada yang diubah.")
            teks = teks.replace(lama, ganti)
        lain[path] = (teks, eol)

    sebelum = snapshot()
    semua = [APP, *lain]
    for path in semua:
        shutil.copyfile(path, path + ".bak")
    tulis(tujuan, isi, eol_app)
    tulis(APP, baru, eol_app)
    for path, (teks, eol) in lain.items():
        tulis(path, teks, eol)

    sesudah = snapshot()
    abaikan = set(tugas.get("boleh_hilang", []))
    beda = [f"  {n}: sebelum={sebelum.get(n)!r:.70} sesudah={sesudah.get(n)!r:.70}"
            for n in sorted((set(sebelum) | set(sesudah)) - abaikan) if sebelum.get(n) != sesudah.get(n)]
    if beda:
        for path in semua:
            shutil.copyfile(path + ".bak", path)
            os.remove(path + ".bak")
        os.remove(tujuan)
        sys.exit("Ada nama/nilai yang berubah; semua berkas dikembalikan:\n" + "\n".join(beda[:20]))

    for path in semua:
        os.remove(path + ".bak")
    print(f"OK: {len(nama)} nama dipindah ke tokobiru/{tugas['modul']}.py, {len(sebelum)} nama di modul app dicek.")
    print(f"{tugas['modul']}.py: {isi.count(chr(10))} baris; app.py: {baru.count(chr(10))} baris.")
    if lain:
        print("Berkas lain disesuaikan: " + ", ".join(os.path.relpath(p, ROOT) for p in lain))
    print("Lanjut: pytest -q -x")


if __name__ == "__main__":
    main(sys.argv[1:])