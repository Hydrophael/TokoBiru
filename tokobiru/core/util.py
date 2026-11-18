"""TokoBiru - fungsi kecil yang dipakai banyak modul."""
from datetime import datetime, timezone


def utcnow():
    """Waktu UTC tanpa zona (naive), sesuai cara MongoDB menyimpan datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_rupiah(amount):
    return "Rp" + f"{amount:,}".replace(",", ".")
