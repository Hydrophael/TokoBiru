"""Gabungkan kode proyek menjadi 1-5 file .txt untuk diupload ke Claude.

Cara pakai (dari folder proyek):
    python pack_code.py .                      -> sampai 5 file (app, backend, frontend, css, tests)
    python pack_code.py . --files 2            -> paksa jadi 2 file saja
    python pack_code.py . --compact            -> hemat token (buang baris kosong & komentar satu baris)
    python pack_code.py . --files 3 --compact --skip tokobiru
    python pack_code.py . --only app backend   -> hanya grup tertentu
    python pack_code.py . --out C:\\Users\\NAMAKAMU\\Desktop\\packed

Grup: app, backend, frontend, css, tests
"""
import argparse
import os
import re

EXTS = {".py", ".js", ".html", ".css"}
# file kecil yang membantu Claude memahami proyek (.env asli sengaja TIDAK dimasukkan)
EXTRA_FILES = {"README.md", "requirements.txt", "requirements-dev.txt", "vercel.json", "pytest.ini", ".env.example"}
SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "__pycache__", ".pytest_cache",
             "dist", "build", ".next", "vendor", "test_receipts", "packed"}
SKIP_FILES = {"pack_code.py", ".env"}
SKIP_SUFFIX = (".min.js", ".min.css")
ORDER = ("app", "backend", "frontend", "css", "tests")

SECRET_RE = re.compile(
    r"((?:key|secret|token|password|passwd)\w*\s*[=:]\s*)(['\"])[^'\"]{8,}\2", re.I)
ENV_RE = re.compile(
    r"^(\s*\w*(?:key|secret|token|password|passwd)\w*\s*=\s*)(\S{8,})\s*$", re.I)


def collect(root, skip_dirs):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d not in skip_dirs]
        for name in sorted(filenames):
            if name in SKIP_FILES or name.endswith(SKIP_SUFFIX):
                continue
            if os.path.splitext(name)[1] in EXTS or name in EXTRA_FILES:
                yield os.path.join(dirpath, name)


def group_of(rel):
    top = rel.split("/")[0]
    if rel == "app.py":
        return "app"
    if top == "tests":
        return "tests"
    if top == "templates":
        return "frontend"
    if top == "static":
        return "css" if rel.endswith(".css") else "frontend"
    return "backend"


def mask_secrets(rel, text):
    hits, out = [], []
    is_env = rel.endswith((".env", ".example"))
    for n, line in enumerate(text.splitlines(), 1):
        new = SECRET_RE.sub(r"\1\2***\2", line)
        if is_env:
            new = ENV_RE.sub(r"\1***", new)
        if new != line:
            hits.append(n)
        out.append(new)
    return "\n".join(out), hits


def compact(rel, text):
    """Buang baris kosong, spasi di ujung baris, dan komentar yang satu baris penuh."""
    ext = os.path.splitext(rel)[1]
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if ext == ".py" and s.startswith("#") and not s.startswith("#!"):
            continue
        if ext == ".js" and s.startswith("//"):
            continue
        if ext == ".css" and s.startswith("/*") and s.endswith("*/"):
            continue
        out.append(line.rstrip())
    return "\n".join(out)


def merge_groups(groups, max_files):
    """Gabungkan grup terkecil sampai jumlah file <= max_files."""
    items = [([name], "".join(parts)) for name, parts in
             sorted(groups.items(), key=lambda kv: ORDER.index(kv[0]))]
    while len(items) > max_files:
        items.sort(key=lambda it: len(it[1]))
        (n1, c1), (n2, c2) = items[0], items[1]
        items = items[2:] + [(n1 + n2, c1 + c2)]
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default="packed")
    ap.add_argument("--skip", nargs="*", default=[], help="nama folder tambahan yang dilewati")
    ap.add_argument("--files", type=int, default=5, help="jumlah maksimal file hasil (1-5)")
    ap.add_argument("--compact", action="store_true", help="hemat token: buang baris kosong & komentar")
    ap.add_argument("--only", nargs="*", choices=ORDER, help="hanya kemas grup ini")
    args = ap.parse_args()
    args.files = max(1, min(args.files, 5))

    groups, sizes, warnings, per_dir = {}, [], [], {}
    saved = 0
    for path in collect(args.root, set(args.skip)):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError):
            print("dilewati:", path)
            continue
        rel = os.path.relpath(path, args.root).replace(os.sep, "/")
        grp = group_of(rel)
        if args.only and grp not in args.only:
            continue
        text, hits = mask_secrets(rel, text)
        warnings += [f"{rel}:{n}" for n in hits]
        if args.compact:
            before = len(text)
            text = compact(rel, text)
            saved += before - len(text)
        sizes.append((len(text), rel))
        top = rel.split("/")[0] if "/" in rel else "(root)"
        per_dir[top] = per_dir.get(top, 0) + 1
        groups.setdefault(grp, []).append(f"\n=== FILE: {rel} ===\n{text.strip()}\n")

    if not groups:
        print("Tidak ada file yang ditemukan.")
        return

    os.makedirs(args.out, exist_ok=True)
    total = 0
    for names, content in merge_groups(groups, args.files):
        out_path = os.path.join(args.out, "+".join(names) + ".txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        total += len(content)
        print(f"{out_path}: {len(content) // 1024} KB, kira-kira {len(content) // 4:,} token")
    print(f"Total kira-kira {total // 4:,} token")
    if args.compact:
        print(f"Hemat dari --compact: kira-kira {saved // 4:,} token")

    print("\n10 file terbesar (kandidat untuk dilewati/dipangkas):")
    for size, rel in sorted(sizes, reverse=True)[:10]:
        print(f"  {size // 1024:>5} KB  {rel}")

    print("\nJumlah file per folder teratas:")
    for top, count in sorted(per_dir.items(), key=lambda x: -x[1]):
        flag = "   <-- banyak sekali, cek / pakai --skip" if count > 100 else ""
        print(f"  {count:>5}  {top}{flag}")

    if warnings:
        print("\nPERHATIAN: nilai di baris ini terdeteksi sebagai key/password dan sudah diganti ***:")
        for w in warnings:
            print("  ", w)


if __name__ == "__main__":
    main()