"""Unduh Webix (JS, CSS, dan font) ke static/. Jalankan sekali dari root proyek:

    python get_webix.py            # versi yang dipakai proyek (DEFAULT_VERSION)
    python get_webix.py 11.4.0     # atau versi lain yang ada di npm (paket "webix")

Hanya memakai pustaka bawaan Python. Hasilnya adalah salinan lokal, jadi CSP di app.py tidak perlu dilonggarkan
dan versi tidak berubah sendiri setelah diunduh.
"""
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

DEFAULT_VERSION = "11.4.0"   # dikunci supaya unduhan ulang tidak mengubah versi diam-diam
version = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VERSION
# Paket npm "webix" lewat jsDelivr: setiap versi tersedia dengan nomor persisnya (cdn.webix.com hanya punya jalur "edge")
base = f"https://cdn.jsdelivr.net/npm/webix@{version}/"
out = Path(__file__).resolve().parent / "static"


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def save(name, data):
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  {path.relative_to(out.parent)}  ({len(data) // 1024} KB)")


print(f"Mengunduh Webix {version} dari {base}")
save("webix.min.js", fetch(base + "webix.min.js"))

css = fetch(base + "webix.min.css")
save("webix.min.css", css)

# CSS memanggil font lewat url(fonts/...): unduh semuanya ke tempat yang sama relatif terhadap CSS
refs = set(re.findall(rb"url\(\s*['\"]?([^)'\"#?]+)", css))
for ref in sorted(refs):
    name = ref.decode()
    if name.startswith(("data:", "http", "//", "/")):
        continue
    try:
        save(name, fetch(urljoin(base, name)))
    except Exception as err:   # satu font gagal tidak membatalkan yang lain
        print(f"  GAGAL {name}: {err}")

print("Selesai")