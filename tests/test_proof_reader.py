"""Tes untuk tokobiru/proof_reader.py. Jalankan: pytest tests/test_proof_reader.py"""
import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

from tokobiru import proof_reader as pr

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
TRANSCRIPT = ("Transfer Berhasil 16 Nov 2026 14:32 WIB Nominal Rp87.500 Biaya admin Rp2.500 Penerima BCA 1234564821 "
              "TOKOBIRU No. Referensi 77310092")


def answer(**override):
    base = {"visible_text": TRANSCRIPT, "is_transfer_proof": True, "status": "Berhasil", "amount_idr": 87500,
            "transfer_time": "2026-11-16 14:32", "timezone": "WIB", "destination": "BCA 1234564821 TOKOBIRU",
            "reference": "77310092", "looks_edited": False, "edit_note": None, "confidence": 0.95}
    base.update(override)
    return json.dumps(base)


class GroundingTests(unittest.TestCase):
    def test_bacaan_yang_ada_di_transkrip_dipertahankan(self):
        got = pr.parse_reading(answer())
        self.assertEqual((got["amount"], got["reference"], got["status"]), (87_500, "77310092", "Berhasil"))
        self.assertEqual(got["time"], datetime(2026, 11, 16, 14, 32))
        self.assertEqual(got["ungrounded"], [])

    def test_nominal_karangan_model_dibuang(self):
        # Struk bernominal 87.500 tetapi model menjawab 78.500: angka itu tidak ada di transkripnya sendiri
        got = pr.parse_reading(answer(amount_idr=78500))
        self.assertIsNone(got["amount"])
        self.assertIn("amount", got["ungrounded"])
        self.assertEqual(evaluate(got)["verdict"], "unclear")     # dibuang -> tidak terbaca, bukan "tidak cocok" palsu

    def test_nominal_dengan_desimal_dan_format_koma_dikenali(self):
        for printed in ("Nominal Rp87.500,00 Penerima TOKOBIRU BCA 1234564821 status Berhasil 14:32",
                        "Nominal IDR 87,500.00 Penerima TOKOBIRU BCA 1234564821 status Berhasil 14:32",
                        "Jumlah 87500 Penerima TOKOBIRU BCA 1234564821 status Berhasil 14:32"):
            self.assertEqual(pr.parse_reading(answer(visible_text=printed))["amount"], 87_500, printed)

    def test_referensi_yang_tidak_tercetak_dibuang_agar_tidak_memicu_duplikat_palsu(self):
        got = pr.parse_reading(answer(reference="99887766"))
        self.assertIsNone(got["reference"])
        self.assertIn("reference", got["ungrounded"])

    def test_referensi_salah_baca_o_dan_nol_tetap_dikenali(self):
        text = TRANSCRIPT.replace("77310092", "TRX O1L2")
        self.assertEqual(pr.parse_reading(answer(visible_text=text, reference="TRX 01I2"))["reference"], "TRX0112")

    def test_jam_dan_zona(self):
        self.assertIsNone(pr.parse_reading(answer(transfer_time="2026-11-16 15:32"))["time"])
        # struk 12 jam: "02:32 PM" ditulis model sebagai 14:32
        pm = TRANSCRIPT.replace("14:32 WIB", "02:32 PM")
        self.assertEqual(pr.parse_reading(answer(visible_text=pm))["time"], datetime(2026, 11, 16, 14, 32))

    def test_nomor_tujuan_harus_ada_di_transkrip(self):
        got = pr.parse_reading(answer(destination="BCA 9999887766 TOKOBIRU"))
        self.assertIsNone(got["destination"])
        self.assertIn("destination", got["ungrounded"])
        self.assertEqual(pr.parse_reading(answer(destination="****4821 TOKOBIRU"))["destination"], "****4821 TOKOBIRU")

    def test_status_karangan_dibuang(self):
        # Model mengisi "Gagal" padahal tidak tercetak: jangan sampai pelanggan jujur dinyatakan gagal
        got = pr.parse_reading(answer(status="Gagal"))
        self.assertIsNone(got["status"])
        self.assertNotEqual(evaluate(got)["reason"], "not_successful")

    def test_tanpa_transkrip_tidak_diperiksa(self):
        got = pr.parse_reading(answer(visible_text=None))
        self.assertEqual((got["amount"], got["ungrounded"]), (87_500, []))
        got = pr.parse_reading(answer(visible_text="pendek"))
        self.assertEqual(got["amount"], 87_500)

    def test_transkrip_tidak_disimpan_di_hasil(self):
        self.assertNotIn("visible_text", pr.parse_reading(answer()))

    def test_tanda_edit_dan_zona_dibaca(self):
        got = pr.parse_reading(answer(looks_edited=True, edit_note="  <b>angka</b> lebih tajam ", timezone="wita"))
        self.assertTrue(got["edited"])
        self.assertNotIn("<", got["edit_note"])
        self.assertEqual(got["timezone"], 8)
        self.assertEqual(pr._timezone("UTC+9"), 9)
        self.assertIsNone(pr._timezone("Jakarta"))
        self.assertFalse(pr.parse_reading('{"looks_edited": "ya"}')["edited"])     # hanya boolean true yang dihitung

    def test_waktu_dengan_detik_atau_penanda_zona_diterima(self):
        for printed in ("2026-11-16 14:32:05", "2026-11-16T14:32", "2026-11-16 14:32 WIB", "2026-11-16 14:32:05+07:00"):
            self.assertEqual(pr._time(printed), datetime(2026, 11, 16, 14, 32), printed)
        for bad in ("2026-11-16 24:10", "16-11-2026 14:32", "2026-11-16"):
            self.assertIsNone(pr._time(bad), bad)


class AccuracyRuleTests(unittest.TestCase):
    def test_berhasil_diproses_bukan_gagal(self):
        for printed in ("Transfer berhasil diproses", "Pembayaran Berhasil Diproses"):
            self.assertEqual(pr._status_kind(printed), "ok", printed)
        for printed in ("Sedang diproses", "Dalam proses", "Unsuccessful", "Not successful", "Dijadwalkan", "Ditolak"):
            self.assertEqual(pr._status_kind(printed), "bad", printed)

    def test_nomor_lain_yang_memuat_empat_digit_di_tengah_tidak_lolos(self):
        self.assertFalse(pr._matches_hint("BCA 1234821567", "4821"))
        self.assertEqual(evaluate(reading(destination="BCA 1234821567"))["verdict"], "mismatch")
        self.assertTrue(pr._matches_hint("BCA 1234564821", "4821"))
        self.assertTrue(pr._matches_hint("****4821", "4821"))
        self.assertTrue(pr._matches_hint("1234564821", "1234564821"))
        self.assertTrue(pr._matches_hint("***4821", "1234564821"))   # hint nomor lengkap, struk tersamar

    def test_nama_pemilik_tahan_spasi_dan_pemotongan(self):
        for printed in ("TOKO BIRU", "Toko-Biru JAYA", "PT TOKOBIRU", "TOKOBIR"):
            self.assertTrue(pr._matches_hint(printed, "TokoBiru"), printed)
        self.assertFalse(pr._matches_hint("BUDI SANTOSO", "TokoBiru"))

    def test_struk_tanpa_data_sejenis_hint_tidak_dinyatakan_salah(self):
        # Hint berupa angka, struk hanya mencetak nama: tidak bisa dipastikan, bukan "bukan rekening toko"
        self.assertEqual(pr.destination_status("TOKO BIRU", "4821"), "unknown")
        self.assertEqual(evaluate(reading(destination="TOKO BIRU"))["verdict"], "unclear")
        # Hint berupa nama, struk hanya mencetak bank dan nomor
        self.assertEqual(pr.destination_status("BCA 1234564821", "TokoBiru"), "unknown")
        self.assertEqual(pr.destination_status("BUDI 9921", "4821,TokoBiru"), "bad")

    def test_status_berhasil_diproses_tidak_membuat_tidak_cocok(self):
        self.assertEqual(evaluate(reading(status="Berhasil diproses"))["verdict"], "match")

    def test_zona_tercetak_memakai_toleransi_ketat(self):
        # 15:50 WITA = 07:50 UTC, NOW = 08:00 UTC: wajar
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 15, 50), timezone=8))["verdict"], "match")
        # 15:50 yang tercetak WIB = 08:50 UTC, hampir satu jam di depan: janggal, padahal tanpa label zona masih ditoleransi
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 15, 50), timezone=7))["verdict"], "suspicious")
        self.assertEqual(evaluate(reading(time=datetime(2026, 11, 16, 15, 50)))["verdict"], "match")
        shown = next(c for c in evaluate(reading(timezone=8))["checks"] if c["key"] == "time")["read"]
        self.assertTrue(shown.endswith("WITA"))

    def test_batas_atas_waktu_adalah_saat_diunggah_bukan_saat_dibaca(self):
        uploaded = datetime(2026, 11, 16, 7, 40)           # 14:40 WIB; dibaca staf baru jam 15:00 WIB
        late = reading(time=datetime(2026, 11, 16, 14, 52), timezone=7)    # 07:52 UTC: setelah foto diunggah
        self.assertEqual(evaluate(late)["verdict"], "match")                         # tanpa uploaded_at lolos karena dibanding NOW
        self.assertEqual(evaluate(late, uploaded_at=uploaded)["verdict"], "suspicious")
        self.assertEqual(evaluate(reading(), uploaded_at=uploaded)["verdict"], "match")

    def test_tanda_edit_dan_unggah_berulang_mencurigakan(self):
        got = evaluate(reading(edited=True, edit_note="angka nominal lebih tajam"))
        self.assertEqual((got["verdict"], got["reason"]), ("suspicious", "tampered"))
        got = evaluate(reading(), revision=pr.REVISION_LIMIT)
        self.assertEqual((got["verdict"], got["reason"]), ("suspicious", "tampered"))
        self.assertEqual(evaluate(reading(), revision=pr.REVISION_LIMIT - 1)["verdict"], "match")

    def test_sidik_jari_transfer(self):
        self.assertEqual(pr.proof_fingerprint(reading()), "87500|202611161432")
        self.assertIsNone(pr.proof_fingerprint(reading(time=None)))
        self.assertIsNone(pr.proof_fingerprint(reading(amount=None)))
        self.assertEqual(evaluate(reading())["fingerprint"], "87500|202611161432")


class ConsensusTests(unittest.TestCase):
    def test_dua_bacaan_sama_menjadi_terkonfirmasi(self):
        got = evaluate(reading(), second=reading())
        self.assertEqual((got["verdict"], got["reads"], got["confirmed"], got["disagree"]), ("match", 2, True, []))
        self.assertEqual(next(c for c in got["checks"] if c["key"] == "consistency")["status"], "ok")

    def test_satu_bacaan_tidak_terkonfirmasi(self):
        got = evaluate(reading())
        self.assertEqual((got["reads"], got["confirmed"]), (1, False))
        self.assertNotIn("consistency", [c["key"] for c in got["checks"]])

    def test_nominal_berbeda_antar_bacaan_menurunkan_cocok_menjadi_perlu_dicek(self):
        got = evaluate(reading(), second=reading(amount=87_000))
        self.assertEqual((got["verdict"], got["reason"], got["disagree"]), ("unclear", "inconsistent", ["nominal"]))
        self.assertFalse(got["confirmed"])

    def test_tidak_cocok_palsu_akibat_salah_baca_digit_juga_diturunkan(self):
        # Bacaan pertama salah (78.500) -> "tidak cocok"; bacaan kedua benar -> jangan menuduh pelanggan
        self.assertEqual(evaluate(reading(amount=78_500))["verdict"], "mismatch")
        got = evaluate(reading(amount=78_500), second=reading())
        self.assertEqual((got["verdict"], got["reason"]), ("unclear", "inconsistent"))

    def test_dua_bacaan_sama_tetap_tidak_cocok(self):
        self.assertEqual(evaluate(reading(amount=78_500), second=reading(amount=78_500))["verdict"], "mismatch")

    def test_perbandingan_kolom(self):
        base = reading()
        cmp = pr.compare_readings
        self.assertEqual(cmp(base, reading()), [])
        self.assertEqual(cmp(base, reading(time=datetime(2026, 11, 16, 14, 33))), ["waktu"])
        self.assertEqual(cmp(base, reading(time=None)), ["waktu"])                     # terbaca vs tidak: beda
        self.assertEqual(cmp(base, reading(reference="99999999")), ["referensi"])
        self.assertEqual(cmp(base, reading(reference=None)), [])                       # salah satu kosong: tidak dibandingkan
        self.assertEqual(cmp(base, reading(destination="BNI 9999 Orang Lain")), ["tujuan"])
        self.assertEqual(cmp(base, reading(destination="****4821")), [])               # nomor tersamar searah
        self.assertEqual(cmp(base, reading(destination="TOKOBIRU")), [])               # tanpa angka: tidak dibandingkan
        self.assertEqual(cmp(reading(status="Berhasil"), reading(status="Gagal")), ["status"])
        self.assertEqual(cmp(base, reading(is_proof=False)), ["jenis foto"])

    def test_hasil_perlu_dicek_tidak_berubah_karena_bacaan_kedua(self):
        got = evaluate(reading(confidence=0.3), second=reading())
        self.assertEqual(got["reason"], "unclear")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReadTests(unittest.TestCase):
    def reply(self, text):
        return FakeResponse(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode())

    def test_permintaan_dan_hasil(self):
        answer = '{"is_transfer_proof": true, "amount_idr": 87500, "confidence": 0.8}'
        with mock.patch("urllib.request.urlopen", return_value=self.reply(answer)) as opened:
            got = pr.read_transfer_proof(b"\xff\xd8\xff-foto", "image/jpeg", "kunci-rahasia", "model-x")
        self.assertEqual(got["amount"], 87_500)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, pr.API_URL.format(model="model-x"))
        self.assertEqual(request.get_header("X-goog-api-key"), "kunci-rahasia")
        self.assertNotIn("kunci-rahasia", request.full_url)          # kunci hanya lewat header
        body = json.loads(request.data)
        self.assertEqual(body["contents"][0]["parts"][0]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("thinkingConfig", body["generationConfig"])   # hanya dipasang untuk gemini-2.5-flash

    def test_gemini_25_flash_mematikan_thinking(self):
        answer = '{"is_transfer_proof": true, "confidence": 0.8}'
        with mock.patch("urllib.request.urlopen", return_value=self.reply(answer)) as opened:
            pr.read_transfer_proof(b"x", "image/png", "k", "models/gemini-2.5-flash")
        request = opened.call_args.args[0]
        self.assertIn("/models/gemini-2.5-flash:generateContent", request.full_url)
        self.assertEqual(json.loads(request.data)["generationConfig"]["thinkingConfig"], {"thinkingBudget": 0})

    def test_pembacaan_teliti_memakai_thinking_medium(self):
        answer = '{"is_transfer_proof": true, "confidence": 0.8}'
        with mock.patch("urllib.request.urlopen", return_value=self.reply(answer)) as opened:
            pr.read_transfer_proof(b"x", "image/png", "k", "gemini-4-hydrogen", thinking="medium")
        config = json.loads(opened.call_args.args[0].data)["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "medium"})
        with mock.patch("urllib.request.urlopen", return_value=self.reply(answer)) as opened:
            pr.read_transfer_proof(b"x", "image/png", "k", "gemini-2.5-flash", thinking="medium")
        self.assertEqual(json.loads(opened.call_args.args[0].data)["generationConfig"]["thinkingConfig"], {"thinkingBudget": 1024})
        with self.assertRaises(pr.ProofReadError):
            pr.read_transfer_proof(b"x", "image/png", "k", "m", thinking="xhigh")

    def test_gemini_4_memakai_thinking_level_rendah(self):
        answer = '{"is_transfer_proof": true, "confidence": 0.8}'
        with mock.patch("urllib.request.urlopen", return_value=self.reply(answer)) as opened:
            pr.read_transfer_proof(b"x", "image/png", "k", "gemini-4-hydrogen")
        request = opened.call_args.args[0]
        self.assertIn("/models/gemini-4-hydrogen:generateContent", request.full_url)
        config = json.loads(request.data)["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertNotIn("temperature", config)
        self.assertGreaterEqual(config["maxOutputTokens"], 2048)

    def test_nama_model_aneh_ditolak_tanpa_memanggil_api(self):
        with mock.patch("urllib.request.urlopen") as opened:
            for bad in ("", "a/b", "m?key=1", "m:generate", "x" * 200):
                with self.assertRaises(pr.ProofReadError):
                    pr.read_transfer_proof(b"x", "image/png", "k", bad)
        opened.assert_not_called()

    def test_bagian_thought_diabaikan(self):
        payload = {"candidates": [{"content": {"parts": [
            {"text": "pikiran { bukan jawaban }", "thought": True},
            {"text": '{"is_transfer_proof": true, "amount_idr": 5000, "confidence": 0.7}'}]}}]}
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            got = pr.read_transfer_proof(b"x", "image/png", "k", "m")
        self.assertEqual(got["amount"], 5_000)

    def test_diblokir_atau_kosong_menjadi_error_jelas(self):
        payload = {"promptFeedback": {"blockReason": "SAFETY"}}
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            with self.assertRaises(pr.ProofReadError) as caught:
                pr.read_transfer_proof(b"x", "image/png", "k", "m")
        self.assertIn("SAFETY", str(caught.exception))

    def test_http_error_tidak_membocorkan_kunci(self):
        error = urllib.error.HTTPError(pr.API_URL, 429, "Too Many", {}, io.BytesIO(b"rate limited"))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(pr.ProofReadError) as caught:
                pr.read_transfer_proof(b"x", "image/png", "kunci-rahasia", "m")
        self.assertIn("429", str(caught.exception))
        self.assertEqual(caught.exception.status, 429)
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("kunci-rahasia", str(caught.exception))

    def test_hanya_galat_sibuk_yang_layak_dicoba_ulang(self):
        for code, expected in ((503, True), (500, True), (429, True), (400, False), (403, False), (404, False)):
            error = urllib.error.HTTPError(pr.API_URL, code, "x", {}, io.BytesIO(b""))
            with mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(pr.ProofReadError) as caught:
                    pr.read_transfer_proof(b"x", "image/png", "k", "m")
            self.assertEqual(caught.exception.retryable, expected, code)
        self.assertFalse(pr.ProofReadError("jaringan putus").retryable)

    def test_jaringan_putus(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(pr.ProofReadError):
                pr.read_transfer_proof(b"x", "image/png", "k", "m")

    def test_format_tidak_didukung_tidak_memanggil_api(self):
        with mock.patch("urllib.request.urlopen") as opened:
            with self.assertRaises(pr.ProofReadError):
                pr.read_transfer_proof(b"x", "image/gif", "k", "m")
        opened.assert_not_called()

    def test_jawaban_kosong(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b'{"candidates": []}')):
            with self.assertRaises(pr.ProofReadError):
                pr.read_transfer_proof(b"x", "image/png", "k", "m")

    def test_resolusi_gambar_tertinggi_dan_prompt_baru(self):
        with mock.patch("urllib.request.urlopen", return_value=self.reply('{"is_transfer_proof": true}')) as opened:
            pr.read_transfer_proof(b"x", "image/png", "k", "model-x")
        config = json.loads(opened.call_args.args[0].data)["generationConfig"]
        self.assertEqual(config["mediaResolution"], "MEDIA_RESOLUTION_HIGH")
        for key in ("visible_text", "timezone", "looks_edited", "digit by digit"):
            self.assertIn(key, pr.SYSTEM_PROMPT)

    def test_batas_waktu_dan_jaringan_putus_layak_dicoba_model_lain(self):
        for error in (urllib.error.URLError("timed out"), TimeoutError("timed out"), ConnectionResetError("putus")):
            with mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(pr.ProofReadError) as caught:
                    pr.read_transfer_proof(b"x", "image/png", "k", "m")
            self.assertTrue(caught.exception.retryable, error)
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"bukan json")):
            with self.assertRaises(pr.ProofReadError) as caught:
                pr.read_transfer_proof(b"x", "image/png", "k", "m")
        self.assertFalse(caught.exception.retryable)       # respons rusak bukan gangguan sementara


class AdviceTests(unittest.TestCase):
    def test_saran_cocok_mengarahkan_ke_mutasi(self):
        # "Cocok" tidak boleh terbaca sebagai izin langsung menandai lunas tanpa cek mutasi
        self.assertIn("mutasi", pr.ADVICE["match"])


if __name__ == "__main__":
    unittest.main()