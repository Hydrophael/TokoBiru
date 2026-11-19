import re

# --- Membandingkan dua pembacaan -----------------------------------------------------------------------------

def _digit_groups(text):
    return [g for g in re.findall(r"\d+", text or "") if len(g) >= 3]


def _digits_related(a, b):
    """Dua tujuan dianggap searah bila ada kelompok angka yang sama atau yang satu akhiran yang lain (nomor tersamar)."""
    return any(x.endswith(y) or y.endswith(x) for x in _digit_groups(a) for y in _digit_groups(b))


def compare_readings(first, second):
    """Daftar kolom yang berbeda antara dua pembacaan foto yang sama. Kosong = konsisten.
    Nominal dan jam harus sama persis (juga bila satu terbaca dan yang lain tidak); referensi dan tujuan dibandingkan
    hanya bila keduanya terbaca."""
    diff = []
    if first["is_proof"] != second["is_proof"]:
        diff.append("jenis foto")
    if first["amount"] != second["amount"]:
        diff.append("nominal")
    if first["time"] != second["time"]:
        diff.append("waktu")
    if first["reference"] and second["reference"] and first["reference"] != second["reference"]:
        diff.append("referensi")
    if _digit_groups(first["destination"]) and _digit_groups(second["destination"]) \
            and not _digits_related(first["destination"], second["destination"]):
        diff.append("tujuan")
    kinds = {_status_kind(first.get("status")), _status_kind(second.get("status"))}
    if kinds == {"ok", "bad"}:
        diff.append("status")
    return diff


def proof_fingerprint(reading):
    """Sidik jari transfer (nominal + menit) untuk mendeteksi struk yang sama difoto/disimpan ulang sehingga byte-nya berbeda."""
    if reading["amount"] is None or reading["time"] is None:
        return None
    return f"{reading['amount']}|{reading['time']:%Y%m%d%H%M}"


# Kata pada status struk. Yang "belum berhasil" diperiksa lebih dulu ('Belum berhasil' mengandung 'berhasil').
_STATUS_BAD = ("belum", "tidak", "pending", "menunggu", "gagal", "fail", "batal", "cancel", "expire", "kedaluwarsa",
               "unpaid", "unsuccess", "not ", "jadwal", "scheduled", "refund", "dikembalikan", "reversed", "ditolak",
               "reject", "declin")


_STATUS_OK = ("berhasil", "sukses", "success", "selesai", "complete", "lunas", "paid", "done")


# 'Sedang diproses' = belum selesai, tetapi 'Berhasil diproses' = selesai: kata ini hanya buruk bila tak ada kata berhasil
_STATUS_SOFT_BAD = ("proses", "processing", "in progress")


def _status_kind(text):
    """'bad' bila status menunjukkan transaksi belum/tidak berhasil, 'ok' bila berhasil, None bila tidak tercetak/tidak dikenal."""
    if not text:
        return None
    lowered = text.casefold()
    if any(word in lowered for word in _STATUS_BAD):
        return "bad"
    if any(word in lowered for word in _STATUS_OK):
        return "ok"
    if any(word in lowered for word in _STATUS_SOFT_BAD):
        return "bad"
    return None