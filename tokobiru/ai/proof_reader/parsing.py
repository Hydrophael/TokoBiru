import json
import re
from datetime import datetime, timedelta


class ProofReadError(Exception):
    """Pembacaan gagal (jaringan, kuota, atau jawaban model tidak bisa dipakai).
    status = kode HTTP bila ada. transient = gangguan sementara (batas waktu, jaringan putus) yang layak dicoba lagi."""

    def __init__(self, message, status=None, transient=False):
        super().__init__(message)
        self.status = status
        self.transient = transient

    @property
    def retryable(self):
        return self.status in RETRYABLE_STATUS or self.transient


MAX_AMOUNT = 10_000_000_000


MIN_TRANSCRIPT = 30                        # transkrip lebih pendek dari ini tidak dipakai untuk memeriksa


# --- Parse jawaban model -------------------------------------------------------------------------------------

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f<>]")


_TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(?:\s*(?:Z|[+-]\d{2}:?\d{2}|WIB|WITA|WIT))?",
                      re.IGNORECASE)


_DIGITS_RE = re.compile(r"\d{1,12}")


_NON_ALNUM_RE = re.compile(r"[^0-9A-Za-z]")


_CANON_TABLE = str.maketrans("OIL", "011")     # O/0 dan I/L/1 sering tertukar saat membaca foto


def _amount(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and _DIGITS_RE.fullmatch(value.strip()):
        value = int(value.strip())
    if isinstance(value, int) and 0 < value <= MAX_AMOUNT:
        return value
    return None


def _time(value):
    """'YYYY-MM-DD HH:MM'. Detik dan penanda zona di belakangnya (yang kadang ikut ditulis model) dibuang."""
    match = _TIME_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match:
        return None
    try:
        return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _timezone(value):
    """Label zona yang tercetak di struk -> selisih jam dari UTC (7, 8, 9), atau None bila tidak tercetak/tidak dikenal."""
    if not isinstance(value, str):
        return None
    upper = value.upper()
    for name, hours in (("WITA", 8), ("WIB", 7), ("WIT", 9)):
        if re.search(rf"\b{name}\b", upper):
            return hours
    match = re.search(r"(?:GMT|UTC)\s*\+\s*(\d{1,2})\b", upper)
    if match and int(match.group(1)) in TZ_NAMES:
        return int(match.group(1))
    return None


def _text(value, limit):
    if not isinstance(value, str):
        return None
    cleaned = " ".join(_CTRL_RE.sub("", value).split())[:limit]
    return cleaned or None


def _canon(text):
    """Hanya huruf/angka, kapital, dan O/I/L disamakan dengan 0/1/1 supaya salah baca satu karakter tidak lolos dari pencocokan."""
    return _NON_ALNUM_RE.sub("", text).upper().translate(_CANON_TABLE)


def _reference(value):
    """Nomor referensi dinormalisasi (hanya huruf/angka, kapital) supaya 'REF 778-899' dan 'ref778899' dianggap sama."""
    text = _text(value, 60)
    if text is None:
        return None
    return _canon(text)[:40] or None


def _confidence(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(value)))


# --- Pemeriksaan silang: setiap klaim model harus ada di transkripnya ----------------------------------------

_NUM_TOKEN_RE = re.compile(r"\d[\d.,]*")


def _transcript_numbers(text):
    """Semua bilangan bulat yang bisa dibaca dari transkrip ('87.500', '87,500', 'Rp87.500,00' -> 87500)."""
    found = set()
    for token in _NUM_TOKEN_RE.findall(text):
        token = token.rstrip(".,")
        digits = re.sub(r"\D", "", token)
        if not digits or len(digits) > 13:
            continue
        found.add(int(digits))
        if len(digits) > 2 and re.search(r"[.,]\d{2}$", token):      # desimal sen: 87.500,00
            found.add(int(digits[:-2]))
    return found


def _time_in_text(moment, text):
    """Jam:menit ada di transkrip. Jam 12 jam (02:32 PM) untuk 14:32 juga diterima."""
    for hour in {moment.hour, moment.hour % 12 or 12}:
        if re.search(rf"(?<!\d)0?{hour}\s?[:.]\s?{moment.minute:02d}(?!\d)", text):
            return True
    return False


def _ground(reading, transcript):
    """Buang (jadikan None) bacaan yang tidak ada di transkrip: itu tanda model menebak atau melengkapi sendiri.
    Mengembalikan daftar nama kolom yang dibuang."""
    dropped = []
    if reading["amount"] is not None and reading["amount"] not in _transcript_numbers(transcript):
        reading["amount"] = None
        dropped.append("amount")
    if reading["time"] is not None and not _time_in_text(reading["time"], transcript):
        reading["time"] = None
        dropped.append("time")
    if reading["reference"] and reading["reference"] not in _canon(transcript):
        reading["reference"] = None
        dropped.append("reference")
    if reading["destination"]:
        digits = re.sub(r"\D", "", transcript)
        groups = [g for g in re.findall(r"\d+", reading["destination"]) if len(g) >= 4]
        if any(g not in digits for g in groups):
            reading["destination"] = None
            dropped.append("destination")
    if reading["status"] and reading["status"].casefold() not in transcript.casefold():
        reading["status"] = None
        dropped.append("status")
    return dropped


def parse_reading(text):
    """Teks jawaban model -> dict yang sudah divalidasi. Melempar ProofReadError bila bukan JSON objek."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ProofReadError("jawaban model tidak berisi JSON")
    try:
        raw = json.loads(text[start:end + 1])
    except ValueError:
        raise ProofReadError("jawaban model bukan JSON yang valid") from None
    if not isinstance(raw, dict):
        raise ProofReadError("jawaban model bukan objek JSON")
    reading = {
        "is_proof": raw.get("is_transfer_proof") is True,
        "amount": _amount(raw.get("amount_idr")),
        "time": _time(raw.get("transfer_time")),
        "timezone": _timezone(raw.get("timezone")),
        "status": _text(raw.get("status"), 40),
        "destination": _text(raw.get("destination"), 80),
        "reference": _reference(raw.get("reference")),
        "confidence": _confidence(raw.get("confidence")),
        "edited": raw.get("looks_edited") is True,
        "edit_note": _text(raw.get("edit_note"), 80),
    }
    transcript = _text(raw.get("visible_text"), 4000)
    # Transkrip hanya dipakai sebagai alat periksa, tidak pernah disimpan atau ditampilkan
    reading["ungrounded"] = _ground(reading, transcript) if transcript and len(transcript) >= MIN_TRANSCRIPT else []
    return reading


RETRYABLE_STATUS = (429, 500, 502, 503, 504)   # server AI sibuk/kuota model habis: layak dicoba dengan model cadangan


TZ_NAMES = {7: "WIB", 8: "WITA", 9: "WIT"}
