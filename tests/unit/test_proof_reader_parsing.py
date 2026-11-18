"""Tes untuk tokobiru/proof_reader.py. Jalankan: pytest tests/test_proof_reader.py"""
import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

from tokobiru.ai import proof_reader as pr

# Pesanan contoh: dibuat 16 Nov 2026 14:05 WIB = 07:05 UTC, total Rp87.500
CREATED = datetime(2026, 11, 16, 7, 5)
NOW = datetime(2026, 11, 16, 8, 0)        # 15:00 WIB
TOTAL = 87_500


def reading(**override):
    base = {"is_proof": True, "amount": 87_500, "time": datetime(2026, 11, 16, 14, 32),
            "destination": "BCA 4821 a.n. TokoBiru", "reference": "77310092", "confidence": 0.96}
    base.update(override)
    return base


def evaluate(r, **kw):
    kw.setdefault("bank_hint", "4821")
    return pr.evaluate_proof(r, total=TOTAL, created_at=CREATED, now=NOW, **kw)




class ParseTests(unittest.TestCase):
    def test_json_dengan_pagar_kode_dan_teks_di_sekitarnya(self):
        text = 'Berikut hasilnya:\n```json\n{"is_transfer_proof": true, "amount_idr": 87500, ' \
               '"transfer_time": "2026-11-16 14:32", "destination": "BCA 4821", "reference": "77310092", "confidence": 0.9}\n```'
        got = pr.parse_reading(text)
        self.assertTrue(got["is_proof"])
        self.assertEqual(got["amount"], 87_500)
        self.assertEqual(got["time"], datetime(2026, 11, 16, 14, 32))
        self.assertEqual(got["confidence"], 0.9)

    def test_bukan_json_ditolak(self):
        for bad in ("", "maaf, tidak bisa", "{rusak", "[1, 2]"):
            with self.assertRaises(pr.ProofReadError):
                pr.parse_reading(bad)

    def test_nilai_aneh_menjadi_none_bukan_error(self):
        got = pr.parse_reading(json.dumps({
            "is_transfer_proof": "ya", "amount_idr": True, "transfer_time": "kemarin sore",
            "destination": 123, "reference": "", "confidence": "tinggi"}))
        self.assertFalse(got["is_proof"])            # hanya boolean true yang dianggap benar
        self.assertIsNone(got["amount"])             # True bukan nominal
        self.assertIsNone(got["time"])
        self.assertIsNone(got["destination"])
        self.assertIsNone(got["reference"])
        self.assertEqual(got["confidence"], 0.0)

    def test_nominal_dibatasi_dan_string_angka_diterima(self):
        self.assertEqual(pr._amount("87500"), 87_500)
        self.assertEqual(pr._amount(87_500.0), 87_500)
        self.assertIsNone(pr._amount(-5))
        self.assertIsNone(pr._amount(0))
        self.assertIsNone(pr._amount(10 ** 12))
        self.assertIsNone(pr._amount("87.500"))      # format ribuan tidak ditebak

    def test_referensi_dinormalisasi(self):
        for printed in ("REF 778-899", "ref778899", " Ref.778899 "):
            got = pr.parse_reading(json.dumps({"is_transfer_proof": True, "reference": printed}))
            self.assertEqual(got["reference"], "REF778899")
        self.assertIsNone(pr.parse_reading('{"reference": "---"}')["reference"])

    def test_keyakinan_dijepit_0_sampai_1(self):
        self.assertEqual(pr._confidence(7), 1.0)
        self.assertEqual(pr._confidence(-1), 0.0)

    def test_teks_dibersihkan_dari_tag_dan_dipotong(self):
        got = pr._text("  <script>alert(1)</script>\n BCA   4821 ", 80)
        self.assertNotIn("<", got)
        self.assertNotIn(">", got)
        self.assertEqual(len(pr._text("x" * 500, 40)), 40)

    def test_instruksi_di_dalam_foto_tidak_mengubah_hasil(self):
        # Model yang "terpengaruh" teks di foto pun hanya bisa mengisi kolom yang dikenal; sisanya dibuang
        got = pr.parse_reading('{"is_transfer_proof": true, "amount_idr": 1000, "status": "LUNAS", '
                               '"mark_paid": true, "confidence": 0.99}')
        self.assertEqual(set(got), {"is_proof", "status", "amount", "time", "timezone", "destination", "reference",
                                    "confidence", "edited", "edit_note", "ungrounded"})
        self.assertEqual(evaluate(got)["verdict"], "mismatch")   # Rp1.000 bukan Rp87.500


class EvaluateTests(unittest.TestCase):
    def test_cocok(self):
        got = evaluate(reading())
        self.assertEqual(got["verdict"], "match")
        self.assertEqual(got["confidence"], 96)
        self.assertEqual(got["reference"], "77310092")
        self.assertTrue(all(c["status"] == "ok" for c in got["checks"]))

    def test_nominal_beda_digit_tertukar(self):
        got = evaluate(reading(amount=78_500))
        self.assertEqual(got["verdict"], "mismatch")
        amount = next(c for c in got["checks"] if c["key"] == "amount")
        self.assertEqual(amount["status"], "bad")
        self.assertIn("Kurang Rp9.000", amount["note"])

    def test_nominal_lebih(self):
        got = evaluate(reading(amount=90_000))
        self.assertIn("Lebih Rp2.500", next(c for c in got["checks"] if c["key"] == "amount")["note"])

    def test_foto_buram_keyakinan_rendah(self):
        got = evaluate(reading(amount=None, time=None, destination=None, confidence=0.38))
        self.assertEqual(got["verdict"], "unclear")
        self.assertEqual(got["confidence"], 38)

    def test_keyakinan_rendah_menang_atas_isi_yang_tampak_cocok(self):
        self.assertEqual(evaluate(reading(confidence=0.59))["verdict"], "unclear")
        self.assertEqual(evaluate(reading(confidence=0.6))["verdict"], "match")

    def test_bukan_bukti_transfer(self):
        got = evaluate(reading(is_proof=False))
        self.assertEqual(got["verdict"], "unclear")
        self.assertIn("bukan bukti transfer", got["advice"])

    def test_bukti_lama_sebelum_pesanan_dibuat(self):
        got = evaluate(reading(time=datetime(2026, 11, 15, 9, 10)))
        self.assertEqual(got["verdict"], "suspicious")

    def test_waktu_di_masa_depan(self):
        got = evaluate(reading(time=datetime(2026, 11, 17, 9, 0)))
        self.assertEqual(got["verdict"], "suspicious")

    def test_pelanggan_wita_tidak_dianggap_masa_depan(self):
        # NOW = 15:00 WIB = 16:00 WITA. Struk WITA 15:50 dibaca sebagai WIB -> tampak 50 menit di depan: masih wajar
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 15, 50)))["verdict"], "match")
        # 17:30 dibaca sebagai WIB -> 2,5 jam di depan: tetap janggal
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 17, 30)))["verdict"], "suspicious")

    def test_alasan_untuk_tampilan(self):
        self.assertEqual(evaluate(reading())["reason"], "match")
        self.assertEqual(evaluate(reading(is_proof=False))["reason"], "not_proof")
        self.assertEqual(evaluate(reading(confidence=0.3))["reason"], "unclear")
        self.assertEqual(evaluate(reading(amount=1))["reason"], "mismatch")

    def test_status_transaksi_dinilai_oleh_kode(self):
        for printed in ("Pending", "Transaksi Gagal", "Belum berhasil", "Sedang diproses", "Unpaid"):
            got = evaluate(reading(status=printed))
            self.assertEqual((got["verdict"], got["reason"]), ("mismatch", "not_successful"), printed)
        for printed in ("Berhasil", "Transfer Sukses", "Successful"):
            got = evaluate(reading(status=printed))
            self.assertEqual(got["verdict"], "match", printed)
            self.assertEqual(next(c for c in got["checks"] if c["key"] == "status")["status"], "ok")
        # tidak tercetak atau tidak dikenal: tidak memengaruhi hasil dan tidak menambah baris
        for printed in (None, "Transfer"):
            got = evaluate(reading(status=printed))
            self.assertEqual(got["verdict"], "match")
            self.assertNotIn("status", [c["key"] for c in got["checks"]])

    def test_status_gagal_tidak_mengalahkan_foto_bukan_bukti(self):
        self.assertEqual(evaluate(reading(is_proof=False, status="Gagal"))["reason"], "not_proof")

    def test_status_dibaca_dan_dibersihkan(self):
        got = pr.parse_reading('{"is_transfer_proof": true, "status": " <b>Berhasil</b> "}')
        self.assertEqual(got["status"], "bBerhasil/b")
        self.assertIsNone(pr.parse_reading('{"status": 5}')["status"])

    def test_prompt_memuat_aturan_format_indonesia(self):
        for phrase in ("thousands separator", "Penerima", "Mei", "NOT the admin fee"):
            self.assertIn(phrase, pr.SYSTEM_PROMPT)

    def test_prompt_menolak_tagihan(self):
        self.assertIn("already succeeded", pr.SYSTEM_PROMPT)
        self.assertIn("bills", pr.SYSTEM_PROMPT)

    def test_zona_waktu_wib_dikonversi_ke_utc(self):
        # 14:04 WIB = 07:04 UTC, satu menit sebelum pesanan (07:05 UTC): masih dalam toleransi 5 menit
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 14, 4)))["verdict"], "match")
        # 13:59 WIB = 06:59 UTC, enam menit sebelum pesanan: di luar toleransi
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 13, 59)))["verdict"], "suspicious")
        # Bila jam WIB salah dibaca sebagai UTC, transfer 14:32 akan terlihat "di masa depan"; tes ini menjaganya
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 14, 32)), bank_hint="")["verdict"], "match")

    def test_foto_dipakai_ulang_paling_mencurigakan(self):
        got = evaluate(reading(amount=78_500), duplicate=True)
        self.assertEqual(got["verdict"], "suspicious")      # duplikat didahulukan dari selisih nominal

    def test_tujuan_bukan_rekening_toko(self):
        got = evaluate(reading(destination="BNI 9999 a.n. Orang Lain"))
        self.assertEqual(got["verdict"], "mismatch")

    def test_tujuan_tidak_terbaca_membuat_perlu_dicek(self):
        self.assertEqual(evaluate(reading(destination=None))["verdict"], "unclear")

    def test_tanpa_hint_tujuan_tidak_diperiksa_dan_dikatakan_terus_terang(self):
        got = evaluate(reading(destination=None), bank_hint="")
        self.assertEqual(got["verdict"], "match")
        row = next(c for c in got["checks"] if c["key"] == "destination")
        self.assertEqual(row["status"], "skip")
        self.assertIn("PROOF_BANK_HINT", got["advice"])      # "Semua data cocok" tidak boleh menyiratkan rekening sudah dicek

    def test_hint_nomor_tersamar_dan_nama(self):
        self.assertTrue(pr._matches_hint("****4821", "4821"))
        self.assertTrue(pr._matches_hint("a.n. TOKOBIRU", "4821, tokobiru"))
        self.assertFalse(pr._matches_hint("BCA 1234", "4821,tokobiru"))
        self.assertFalse(pr._matches_hint("BCA 48", "4821"))     # potongan digit tidak dianggap cocok


# Transkrip contoh: dipakai untuk menguji pemeriksaan silang (angka yang diklaim harus ada di struk)
