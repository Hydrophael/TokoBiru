"""Pemindah blok kode dari app.py ke modul di paket tokobiru/, satu tugas per langkah refactor.

Aman dijalankan ulang. Sebelum dan sesudah memindah, semua nama dan nilai di modul `app`
dibandingkan; bila ada yang berbeda, app.py dikembalikan seperti semula.

Jalankan dari akar proyek:  python scripts/pindah_blok.py serializers
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

# Tiap tugas: modul tujuan, kepala berkas, dan potongan app.py (dari penanda awal sampai sebelum penanda akhir)
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
    nama = nama_didefinisikan(blok)

    sisa = teks
    for awal, akhir in sorted(rentang, reverse=True):
        sisa = sisa[:awal] + sisa[akhir:].lstrip("\n")
    kait = sisa.index(JANGKAR)
    ujung = sisa.index("\n", kait) + 1
    daftar = ",\n    ".join(nama)
    impor = f"from tokobiru.{tugas['modul']} import (  # noqa: F401,E402\n    {daftar},\n)\n"
    sisa = sisa[:ujung] + impor + sisa[ujung:]
    while "\n\n\n\n" in sisa:
        sisa = sisa.replace("\n\n\n\n", "\n\n\n")
    return sisa, tugas["kepala"] + blok, nama


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


def main(argv):
    if len(argv) != 1 or argv[0] not in TUGAS:
        sys.exit("Pakai: python scripts/pindah_blok.py <" + "|".join(TUGAS) + ">")
    tugas = TUGAS[argv[0]]
    tujuan = os.path.join(ROOT, "tokobiru", tugas["modul"] + ".py")
    if os.path.exists(tujuan):
        print(f"tokobiru/{tugas['modul']}.py sudah ada; tidak ada yang dikerjakan.")
        return

    with open(APP, encoding="utf-8", newline="") as fh:
        mentah = fh.read()
    crlf = "\r\n" in mentah
    baru, isi, nama = potong(mentah.replace("\r\n", "\n"), tugas)
    kurang = nama_bebas(isi)
    if kurang:
        sys.exit("Modul baru memakai nama yang belum diimpor: " + ", ".join(kurang) + "\nTidak ada yang diubah.")

    sebelum = snapshot()
    cadangan = APP + ".bak"
    shutil.copyfile(APP, cadangan)
    eol = "\r\n" if crlf else "\n"
    with open(tujuan, "w", encoding="utf-8", newline="") as fh:
        fh.write(isi.replace("\n", eol))
    with open(APP, "w", encoding="utf-8", newline="") as fh:
        fh.write(baru.replace("\n", eol))

    sesudah = snapshot()
    beda = [f"  {n}: sebelum={sebelum.get(n)!r:.70} sesudah={sesudah.get(n)!r:.70}"
            for n in sorted(set(sebelum) | set(sesudah)) if sebelum.get(n) != sesudah.get(n)]
    if beda:
        shutil.copyfile(cadangan, APP)
        os.remove(tujuan)
        sys.exit("Ada nama/nilai yang berubah; app.py dikembalikan:\n" + "\n".join(beda[:20]))

    os.remove(cadangan)
    print(f"OK: {len(nama)} nama dipindah ke tokobiru/{tugas['modul']}.py, {len(sebelum)} nama di modul app identik.")
    print(f"{tugas['modul']}.py: {isi.count(chr(10))} baris; app.py: {baru.count(chr(10))} baris.")
    print("Lanjut: pytest -q -x")


if __name__ == "__main__":
    main(sys.argv[1:])