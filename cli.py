import base64
import getpass
import sys

from pymongo.errors import DuplicateKeyError

from tokobiru.core.connection import ensure_indexes, get_db
from tokobiru.errors import ApiError
from tokobiru.services.bootstrap import DEMO_PASSWORD, DEMO_USERS, seed_demo
from tokobiru.services.users import new_user_doc, user_form


def create_master_cli():
    answers = {
        "name": input("Nama lengkap : "),
        "username": input("Username     : "),
        "email": input("Email        : "),
        "password": getpass.getpass("Password     : "),
    }
    try:
        clean = user_form(answers)
    except ApiError as e:
        for message in e.fields.values():
            print(f"  - {message}")
        sys.exit(1)
    try:
        get_db().users.insert_one(new_user_doc(clean, "master"))
    except DuplicateKeyError:
        print("Username atau email sudah terdaftar.")
        sys.exit(1)
    print(f"Akun master '{clean['username']}' dibuat.")


def gen_vapid_cli():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())

    def b64(raw):
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    private = b64(key.private_numbers().private_value.to_bytes(32, "big"))
    public = b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    print("Salin ke Environment Variables (Vercel) atau .env. Jaga kunci privat, jangan dibagikan.\n")
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:emailanda@contoh.com")


def seed_demo_cli():
    created = seed_demo(get_db())
    print("Akun demo (password semua: %s):" % DEMO_PASSWORD)
    for _, username, _, role in DEMO_USERS:
        print(f"  {role:<7} {username}" + ("" if username in created else "  (sudah ada)"))


def ensure_indexes_cli():
    failed = ensure_indexes(get_db())
    if failed:
        print("Indeks yang gagal dibuat (lihat pesan galat di atas):")
        for name in failed:
            print(f"  - {name}")
        sys.exit(1)
    print("Semua indeks siap.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "create-master":
        create_master_cli()
    elif cmd == "seed-demo":
        seed_demo_cli()
    elif cmd == "gen-vapid":
        gen_vapid_cli()
    elif cmd == "ensure-indexes":
        ensure_indexes_cli()
    else:
        print("Perintah: python cli.py [create-master | seed-demo | gen-vapid | ensure-indexes]")
        sys.exit(1)


if __name__ == "__main__":
    main()