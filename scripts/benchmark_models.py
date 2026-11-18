"""
Uji cepat model Gemini untuk pembaca bukti transfer TokoBiru: mana yang ada di akun Anda, dan seberapa cepat.

Memakai proof_reader.read_transfer_proof yang SAMA dengan aplikasi (permintaan, pengaturan berpikir, dan penguraian
jawaban identik), jadi hasilnya mewakili apa yang terjadi di aplikasi. Jalankan di folder proyek, dari jaringan/server
yang sama dengan aplikasi (kecepatan sangat bergantung pada jaringan):

  python scripts/benchmark_models.py test_receipts/01_cocok.png                      # semua model kandidat, mode cepat (seperti saat unggah)
  python scripts/benchmark_models.py test_receipts/01_cocok.png --manual             # mode teliti (seperti tombol "Baca dengan AI")
  python scripts/benchmark_models.py test_receipts/01_cocok.png gemini-3.5-flash-lite gemini-2.5-flash   # hanya model tertentu

Kunci diambil dari GEMINI_API_KEY (lingkungan, atau berkas .env di folder ini). Kunci tidak pernah dicetak.
Gambar uji: buat dengan scripts/generate_test_receipts.py, atau pakai tangkapan layar struk asli (jangan bagikan struk asli ke orang lain).
"""
import mimetypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # akar proyek
from tokobiru import proof_reader as pr  # noqa: E402

KANDIDAT = [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash",
]
BATAS_DETIK = 30   # sengaja longgar supaya kelihatan berapa lama sebenarnya, bukan sekadar "gagal"


def ambil_kunci():
    kunci = os.environ.get("GEMINI_API_KEY", "").strip()
    if not kunci and os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for baris in f:
                nama, _, nilai = baris.strip().partition("=")
                if nama.strip() == "GEMINI_API_KEY":
                    kunci = nilai.strip().strip('"').strip("'")
    return kunci


def jalankan(model, gambar, mime, kunci, berpikir):
    mulai = time.monotonic()
    try:
        hasil = pr.read_transfer_proof(gambar, mime, kunci, model, timeout=BATAS_DETIK, thinking=berpikir)
    except pr.ProofReadError as exc:
        detik = time.monotonic() - mulai
        if exc.status == 404:
            keterangan = "TIDAK ADA di akun ini (404) - jangan dipakai"
        elif exc.status in (400, 403):
            keterangan = f"DITOLAK ({exc.status}) - cek kunci/pengaturan: {str(exc)[:80]}"
        elif exc.status == 429:
            keterangan = "kena batas kuota (429) - coba lagi nanti / naikkan paket"
        elif exc.transient:
            keterangan = f"tidak ada jawaban dalam {BATAS_DETIK} dtk: {str(exc)[:80]}"
        else:
            keterangan = str(exc)[:100]
        return detik, False, keterangan
    detik = time.monotonic() - mulai
    ringkas = f"nominal={hasil['amount']} referensi={hasil['reference']} bukti={hasil['is_proof']} yakin={hasil['confidence']}"
    return detik, True, ringkas


def main(argv):
    manual = "--manual" in argv
    argumen = [a for a in argv if not a.startswith("--")]
    if not argumen:
        print(__doc__)
        return 2
    path, model_pilihan = argumen[0], argumen[1:]
    kunci = ambil_kunci()
    if not kunci:
        print("GEMINI_API_KEY tidak ditemukan (lingkungan maupun .env).")
        return 2
    if not os.path.exists(path):
        print(f"Gambar tidak ditemukan: {path}")
        return 2
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        gambar = f.read()

    berpikir = "medium" if manual else "low"
    print(f"Gambar {os.path.basename(path)} ({len(gambar) // 1024} KB), mode {'teliti (manual)' if manual else 'cepat (unggah)'}\n")
    print(f"{'model':<24}{'detik':>7}  hasil")
    hasil_sukses = []
    for model in (model_pilihan or KANDIDAT):
        detik, ok, keterangan = jalankan(model, gambar, mime, kunci, berpikir)
        print(f"{model:<24}{detik:>7.1f}  {'OK  ' if ok else 'GAGAL'} {keterangan}")
        if ok:
            hasil_sukses.append((detik, model))

    batas = 13 if manual else 6
    print(f"\nBatas waktu aplikasi: unggah 6 dtk, baca manual 20 dtk (model utama dapat sekitar {batas} dtk).")
    cepat = sorted(hasil_sukses)
    if cepat:
        print("Yang berhasil, dari tercepat:", ", ".join(f"{m} ({d:.1f} dtk)" for d, m in cepat))
        layak = [m for d, m in cepat if d < batas * 0.7]
        if len(layak) >= 2:
            print(f"Saran awal: PROOF_READER_MODEL={layak[0]}  PROOF_READER_FALLBACK_MODEL={layak[1]}")
            print("(ulangi 2-3 kali: kecepatan berubah-ubah, dan pastikan nominal/referensi terbaca benar)")
        else:
            print("Belum ada dua model yang cukup cepat; ulangi beberapa kali atau coba dari server/jaringan lain.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))