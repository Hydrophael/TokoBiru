"""
Pembuat gambar struk UJI (sintetis) untuk menguji pembaca bukti transfer TokoBiru.

BUKAN struk asli dan sengaja tidak meniru tampilan bank mana pun ("Bank Contoh", tanpa logo, ada tulisan DATA UJI).
Gunanya menguji aturan di proof_reader.py. Untuk akurasi pada struk bank sungguhan, tetap uji dengan tangkapan layar asli.

Cara pakai (urutannya penting, jam di struk dibuat dari waktu SEKARANG):
  1. pip install pillow
  2. Buat pesanan transfer di toko, catat TOTAL-nya (mis. 87500).
  3. Isi PROOF_BANK_HINT di .env sesuai --rekening / --nama di bawah (mis. 4821 atau TokoBiru), lalu jalankan ulang server.
  4. python scripts/generate_test_receipts.py      (akan menanyakan total; atau langsung: --total 87500 --rekening 1234564821 --nama TOKOBIRU)
  5. Unggah satu gambar per pesanan (folder test_receipts/, daftar hasil yang diharapkan ada di test_receipts/expected.csv).
     Satu pesanan = satu gambar, kecuali 14_salinan_dari_01 yang diunggah ke pesanan LAIN setelah 01 dibaca.
"""
import argparse
import csv
import io
import os
import random
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIB = timezone(timedelta(hours=7))
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
BOLD_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def font(size, bold=False):
    for path in (BOLD_CANDIDATES if bold else FONT_CANDIDATES):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def rupiah(n):
    return "Rp" + f"{n:,}".replace(",", ".")


def tanggal(dt, jam12=False, zona="WIB"):
    jam = dt.strftime("%I:%M:%S %p") if jam12 else dt.strftime("%H:%M:%S")
    return f"{dt.day:02d} {BULAN[dt.month - 1]} {dt.year}, {jam}" + (f" {zona}" if zona else "")


def struk(*, judul="Transfer Berhasil", status="Berhasil", nominal, biaya=2500, waktu, jam12=False, zona="WIB",
          bank_tujuan="Bank Contoh", rekening="1234564821", nama="TOKOBIRU", referensi, pengirim="BUDI SANTOSO"):
    """Gambar struk bergaya aplikasi bank generik, ukuran seperti tangkapan layar HP."""
    w, h = 1080, 1900
    img = Image.new("RGB", (w, h), "#f4f6f8")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 150], fill="#0b6e6e")
    d.text((50, 55), "Bank Contoh Mobile", font=font(44, True), fill="white")
    # lingkaran centang
    ok = status.lower().startswith(("berhasil", "sukses")) or "berhasil" in status.lower()
    warna = "#1f9d55" if ok else "#d98e04"
    d.ellipse([w / 2 - 70, 210, w / 2 + 70, 350], fill=warna)
    if ok:
        d.line([(w / 2 - 35, 282), (w / 2 - 8, 312), (w / 2 + 40, 248)], fill="white", width=14)
    else:
        d.text((w / 2 - 12, 245), "!", font=font(90, True), fill="white")
    d.text((w / 2, 400), judul, font=font(54, True), fill="#1b2a38", anchor="mm")
    d.text((w / 2, 465), tanggal(waktu, jam12, zona), font=font(34), fill="#5b6b79", anchor="mm")
    d.rounded_rectangle([40, 520, w - 40, 1620], radius=28, fill="white")

    baris = [
        ("Status", status),
        ("Nominal", rupiah(nominal)),
        ("Biaya admin", rupiah(biaya)),
        ("Total", rupiah(nominal + biaya)),
        None,
        ("Penerima", nama),
        ("Bank tujuan", f"{bank_tujuan} - {rekening}"),
        None,
        ("Pengirim", pengirim),
        ("No. Referensi", referensi),
    ]
    y = 570
    for item in baris:
        if item is None:
            d.line([(80, y + 10), (w - 80, y + 10)], fill="#e3e8ee", width=3)
            y += 45
            continue
        label, nilai = item
        d.text((80, y), label, font=font(34), fill="#6b7a88")
        d.text((w - 80, y), nilai, font=font(38, True), fill="#1b2a38", anchor="ra")
        y += 100
    d.text((w / 2, 1690), "Simpan struk ini sebagai bukti transfer", font=font(30), fill="#8a97a3", anchor="mm")
    d.text((w / 2, 1830), "DATA UJI - bukan bukti pembayaran asli", font=font(30, True), fill="#c0392b", anchor="mm")
    return img


def halaman_tagihan(total, waktu):
    """Halaman 'menunggu pembayaran': bukan bukti transfer."""
    w, h = 1080, 1600
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((w / 2, 140), "Menunggu Pembayaran", font=font(58, True), fill="#d98e04", anchor="mm")
    d.text((w / 2, 230), "Selesaikan pembayaran sebelum " + tanggal(waktu + timedelta(hours=1)), font=font(32), fill="#5b6b79", anchor="mm")
    d.text((w / 2, 340), "Total tagihan " + rupiah(total), font=font(48, True), fill="#1b2a38", anchor="mm")
    rnd = random.Random(7)
    for gx in range(14):
        for gy in range(14):
            if rnd.random() < 0.5:
                d.rectangle([260 + gx * 40, 450 + gy * 40, 296 + gx * 40, 486 + gy * 40], fill="black")
    d.text((w / 2, 1100), "Scan kode QR untuk membayar", font=font(34), fill="#5b6b79", anchor="mm")
    d.text((w / 2, 1520), "DATA UJI - bukan bukti pembayaran asli", font=font(30, True), fill="#c0392b", anchor="mm")
    return img


def simpan(img, folder, nama, jpeg_quality=None):
    ext = "jpg" if jpeg_quality else "png"
    path = os.path.join(folder, f"{nama}.{ext}")
    if jpeg_quality:
        img.convert("RGB").save(path, "JPEG", quality=jpeg_quality)
    else:
        img.save(path, "PNG")
    return os.path.basename(path)


def main():
    ap = argparse.ArgumentParser(description="Buat gambar struk uji sintetis")
    ap.add_argument("--total", type=int, help="total pesanan dalam rupiah, mis. 87500 (bila kosong, akan ditanyakan)")
    ap.add_argument("--rekening", default="1234564821", help="nomor rekening toko (4 digit terakhir harus sama dengan PROOF_BANK_HINT)")
    ap.add_argument("--nama", default="TOKOBIRU", help="nama pemilik rekening toko")
    ap.add_argument("--out", default="test_receipts", help="folder hasil")
    a = ap.parse_args()
    while a.total is None:
        isi = input("Total pesanan transfer (rupiah, angka saja, mis. 87500): ").strip().replace(".", "")
        if isi.isdigit():
            a.total = int(isi)
        else:
            print("Isi dengan angka saja.")
    if a.total < 1000:
        ap.error("--total minimal 1000")
    os.makedirs(a.out, exist_ok=True)

    sekarang = datetime.now(WIB).replace(tzinfo=None)
    waktu = sekarang - timedelta(minutes=1)
    rnd = random.Random()
    ref = lambda: str(rnd.randint(10**9, 10**10 - 1))
    basis = dict(nominal=a.total, waktu=waktu, rekening=a.rekening, nama=a.nama)
    hasil = []

    def tambah(kode, img, harapan, catatan, jpeg=None):
        hasil.append((simpan(img, a.out, kode, jpeg), harapan, catatan))

    r1 = ref()
    asli = struk(referensi=r1, **basis)
    tambah("01_cocok", asli, "Cocok", "Semua benar. Nominal dan Total (dengan biaya admin) berbeda: AI harus memakai Nominal.")
    tambah("02_nominal_kurang", struk(referensi=ref(), **dict(basis, nominal=a.total - 9000)), "Tidak cocok", "Nominal kurang Rp9.000.")
    tambah("03_nominal_lebih", struk(referensi=ref(), **dict(basis, nominal=a.total + 2500)), "Tidak cocok", "Nominal lebih Rp2.500.")
    tambah("04_tujuan_lain", struk(referensi=ref(), **dict(basis, rekening="9988776655", nama="ORANG LAIN")), "Tidak cocok", "Rekening tujuan bukan milik toko.")
    tambah("05_status_diproses", struk(referensi=ref(), judul="Transfer Diproses", status="Diproses", **basis), "Tidak cocok", "Transaksi belum berhasil.")
    tambah("06_berhasil_diproses", struk(referensi=ref(), status="Berhasil diproses", **basis), "Cocok", "Kata 'diproses' tidak boleh membuatnya dianggap gagal.")
    tambah("07_struk_kemarin", struk(referensi=ref(), **dict(basis, waktu=waktu - timedelta(days=1))), "Mencurigakan", "Jam transfer sebelum pesanan dibuat.")
    tambah("08_zona_wita", struk(referensi=ref(), zona="WITA", **dict(basis, waktu=waktu + timedelta(hours=1))), "Cocok", "Jam WITA (+1 jam) dengan label zona tercetak.")
    tambah("09_jam_12_pm", struk(referensi=ref(), jam12=True, **basis), "Cocok", "Jam format 12 jam (AM/PM).")
    tambah("10_nomor_tersamar", struk(referensi=ref(), **dict(basis, rekening="******" + a.rekening[-4:])), "Cocok", "Nomor rekening tersamar, nama pemilik tetap tercetak.")

    buram = asli.resize((300, 528)).filter(ImageFilter.GaussianBlur(2)).resize((1080, 1900))
    tambah("11_buram", buram, "Perlu dicek", "Sangat buram: AI tidak boleh menebak angka.", jpeg=25)
    tambah("12_terpotong", asli.crop((0, 1000, 1080, 1900)), "Perlu dicek", "Bagian atas (nominal, tanggal) terpotong.")
    tambah("13_bukan_struk", halaman_tagihan(a.total, waktu), "Perlu dicek", "Halaman tagihan 'menunggu pembayaran', bukan bukti.")

    # Salinan struk 01 dengan byte berbeda (kompres ulang + diperkecil): lolos dari pemeriksaan sha256, harus tertangkap
    # lewat nomor referensi yang sama. Unggah ke pesanan LAIN setelah 01 dibaca.
    buf = io.BytesIO()
    asli.resize((900, 1583)).convert("RGB").save(buf, "JPEG", quality=70)
    tambah("14_salinan_dari_01", Image.open(io.BytesIO(buf.getvalue())), "Mencurigakan",
           "Struk 01 disimpan ulang. Unggah ke pesanan KEDUA setelah 01 dibaca.", jpeg=70)

    with open(os.path.join(a.out, "expected.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["file", "hasil_yang_diharapkan", "catatan"])
        wr.writerows(hasil)

    print(f"{len(hasil)} gambar dibuat di '{a.out}/' (jam struk: {tanggal(waktu)}).")
    print("Buat pesanan transfer BARU untuk tiap gambar (total", rupiah(a.total) + "), lalu unggah. Daftar harapan: expected.csv")
    print("PROOF_BANK_HINT yang cocok dengan struk ini:", a.rekening[-4:], "atau", a.nama)


if __name__ == "__main__":
    main()