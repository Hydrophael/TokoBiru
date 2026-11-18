"""Langkah 5a: pindahkan blok konfigurasi app.py ke tokobiru/config.py.

Aman dijalankan ulang. Skrip membandingkan semua nama dan nilai konstanta di modul `app`
sebelum dan sesudah; bila ada yang berbeda, app.py dikembalikan seperti semula.

Jalankan dari akar proyek:  python scripts/split_config.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "scripts" else os.getcwd()
APP = os.path.join(ROOT, "app.py")
PKG = os.path.join(ROOT, "tokobiru")
CONFIG = os.path.join(PKG, "config.py")

START = 'IS_VERCEL = bool(os.environ.get("VERCEL"))'
END = "def utcnow():"

SNAPSHOT = r"""
import json, os, sys, types
sys.path.insert(0, os.getcwd())
import app

RANDOM = {"DUMMY_HASH"}   # hash dengan garam acak: berbeda tiap proses


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


out = {}
for name in dir(app):
    if name.startswith("__"):
        continue
    out[name] = "<random>" if name in RANDOM else canon(getattr(app, name))
print("@@" + json.dumps(out, sort_keys=True, default=repr))
"""


def snapshot():
    result = subprocess.run([sys.executable, "-c", SNAPSHOT], cwd=ROOT, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            return json.loads(line[2:])
    sys.exit("Gagal membaca app.py:\n" + result.stderr[-1500:])


def main():
    if os.path.exists(CONFIG):
        print("tokobiru/config.py sudah ada; tidak ada yang dikerjakan.")
        return

    with open(APP, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")

    start = text.index(START)
    end = text.index("\n" + END, start) + 1
    block = text[start:end]

    # Bagian yang harus tetap di app.py: objek Flask dan state koneksi
    app_re = re.compile(r"app = Flask\(__name__\)\napp\.config\.update\(\n(?:.*\n)*?\)\n\n?")
    match = app_re.search(block)
    if not match:
        sys.exit("Blok 'app = Flask(...)' tidak ditemukan; tidak ada yang diubah.")
    app_block = match.group(0).rstrip("\n") + "\n"
    block = block.replace(match.group(0), "")
    if "_db = None\n" not in block:
        sys.exit("'_db = None' tidak ditemukan; tidak ada yang diubah.")
    block = block.replace("_db = None\n", "")
    block = re.sub(r"\n{4,}", "\n\n\n", block).strip("\n") + "\n"

    header = (
        '"""TokoBiru - konfigurasi: environment variable dan konstanta aplikasi.\n\n'
        "Semua nilai dibaca sekali saat modul diimpor. Modul lain memakainya lewat\n"
        "`from tokobiru import config` lalu `config.NAMA`, atau (sementara, selama app.py\n"
        'masih besar) lewat `from tokobiru.config import *`.\n"""\n'
        "import os\nimport re\nimport sys\nfrom datetime import timedelta\n\n"
    )
    config_text = header + block.replace(
        'BASE_DIR = os.path.dirname(os.path.abspath(__file__))',
        "BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # akar proyek (satu tingkat di atas paket ini)")

    replacement = (
        "from tokobiru.config import *  # noqa: F401,F403,E402  (sementara: nama-nama lama tetap bisa dipakai di sini)\n"
        "from tokobiru.config import _env_int, _env_str  # noqa: F401,E402\n\n"
        + app_block + "\n_db = None\n\n\n"
    )
    new_text = text[:start] + replacement + text[end:].lstrip("\n")

    before = snapshot()

    backup = APP + ".bak"
    shutil.copyfile(APP, backup)
    os.makedirs(PKG, exist_ok=True)
    init = os.path.join(PKG, "__init__.py")
    if not os.path.exists(init):
        with open(init, "w", encoding="utf-8", newline="") as fh:
            fh.write('"""Paket TokoBiru."""\n')
    eol = "\r\n" if crlf else "\n"
    with open(CONFIG, "w", encoding="utf-8", newline="") as fh:
        fh.write(config_text.replace("\n", eol))
    with open(APP, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text.replace("\n", eol))

    after = snapshot()
    problems = []
    for name in sorted(set(before) | set(after)):
        if name in ("os", "re", "sys", "timedelta") and name in after:
            continue
        if before.get(name) != after.get(name):
            problems.append(f"  {name}: sebelum={before.get(name)!r:.70} sesudah={after.get(name)!r:.70}")
    if problems:
        shutil.copyfile(backup, APP)
        os.remove(CONFIG)
        sys.exit("Ada nama/nilai yang berubah; app.py dikembalikan:\n" + "\n".join(problems[:20]))

    os.remove(backup)
    print(f"OK: {len(before)} nama di modul app identik sebelum dan sesudah.")
    print(f"tokobiru/config.py: {config_text.count(chr(10))} baris; app.py: {new_text.count(chr(10))} baris.")


if __name__ == "__main__":
    main()