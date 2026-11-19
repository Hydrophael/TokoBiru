"""Hitungan laporan penjualan tanpa database: tanggal WIB, ongkir, dan produk terlaris."""
from datetime import date, datetime

import pytest

from tokobiru.core.config import WIB_OFFSET
from tokobiru.errors import ApiError
from tokobiru.services.stats import build_report, report_group, report_range


def utc(tahun, bulan, hari, jam_wib=0):
    return datetime(tahun, bulan, hari, jam_wib) - WIB_OFFSET


def pesanan(paid_at, subtotal, ongkir=0, items=()):
    return {"paid_at": paid_at, "created_at": paid_at, "subtotal": subtotal,
            "shipping_fee": ongkir, "total": subtotal + ongkir, "items": list(items)}


def test_tanggal_bayar_dipetakan_ke_hari_wib():
    data = [pesanan(utc(2026, 11, 18, 23), 50000), pesanan(utc(2026, 11, 19, 0), 5000)]
    hasil = build_report(data, date(2026, 11, 17), date(2026, 11, 19), "day")
    assert [(p["key"], p["revenue"], p["orders"]) for p in hasil["series"]] == [
        ("2026-11-17", 0, 0), ("2026-11-18", 50000, 1), ("2026-11-19", 5000, 1)]


def test_ongkir_terpisah_dan_pesanan_lama_tanpa_subtotal():
    baru = pesanan(utc(2026, 11, 18, 10), 50000, ongkir=10000)
    lama = {"paid_at": utc(2026, 11, 18, 11), "total": 7000, "items": []}
    ringkasan = build_report([baru, lama], date(2026, 11, 18), date(2026, 11, 18), "day")["summary"]
    assert ringkasan["revenue"] == 57000 and ringkasan["shipping"] == 10000
    assert ringkasan["average"] == 28500


def test_per_bulan_mengisi_bulan_kosong():
    hasil = build_report([pesanan(utc(2026, 11, 2, 9), 1000)], date(2026, 9, 20), date(2026, 11, 19), "month")
    assert [(p["key"], p["revenue"]) for p in hasil["series"]] == [("2026-09", 0), ("2026-10", 0), ("2026-11", 1000)]


def test_produk_terlaris_urut_jumlah_lalu_omzet():
    item = lambda pid, nama, qty, sub: {"product_id": pid, "name": nama, "qty": qty, "subtotal": sub}
    data = [pesanan(utc(2026, 11, 18, 9), 50000, items=[item("a", "Teh", 2, 20000), item("b", "Gula", 3, 30000)]),
            pesanan(utc(2026, 11, 18, 10), 5000, items=[item("a", "Teh", 1, 5000)])]
    top = build_report(data, date(2026, 11, 18), date(2026, 11, 18), "day")["top_products"]
    assert [(p["name"], p["qty"], p["revenue"]) for p in top] == [("Gula", 3, 30000), ("Teh", 3, 25000)]


@pytest.mark.parametrize("dari,sampai", [("x", "2026-11-19"), ("2026-11-20", "2026-11-19"), ("2025-01-01", "2026-11-19")])
def test_rentang_tidak_valid(dari, sampai):
    with pytest.raises(ApiError) as galat:
        report_range(dari, sampai)
    assert galat.value.status == 422


def test_rentang_bawaan_30_hari_dan_grup_otomatis():
    awal, akhir = report_range("", "2026-11-19")
    assert (akhir - awal).days == 29
    assert report_group("", 30) == "day" and report_group("day", 200) == "month" and report_group("month", 7) == "month"