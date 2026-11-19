from datetime import date, datetime, timedelta

from tokobiru.core.config import (
    ORDER_STATUS,
    REPORT_DAILY_MAX_DAYS,
    REPORT_DEFAULT_DAYS,
    REPORT_MAX_DAYS,
    REVENUE_STATUS,
    TOP_PRODUCTS_SIZE,
    WIB_OFFSET,
)
from tokobiru.core.util import utcnow
from tokobiru.errors import ApiError

# Omzet hanya nilai barang. Pesanan lama tanpa subtotal dibuat sebelum ada ongkir, jadi total sama dengan subtotal
OMZET = {"$ifNull": ["$subtotal", "$total"]}
# COD yang masih dikirim belum dihitung: uangnya baru diterima saat selesai
BELUM_DITERIMA = {"cod": True, "status": "shipped"}


def omzet_pesanan(order):
    subtotal = order.get("subtotal")
    return order["total"] if subtotal is None else subtotal


def awal_hari_wib(day):
    """Pukul 00.00 WIB pada tanggal `day`, dalam UTC tanpa zona seperti yang disimpan MongoDB."""
    return datetime(day.year, day.month, day.day) - WIB_OFFSET


def order_summary(db):
    by_status = {status: 0 for status in ORDER_STATUS}
    revenue = paid_orders = 0
    pipeline = [{"$group": {"_id": {"status": "$status", "cod": {"$eq": ["$cod", True]}},
                            "n": {"$sum": 1}, "sum": {"$sum": OMZET}}}]
    for row in db.orders.aggregate(pipeline):
        status, cod = row["_id"]["status"], row["_id"].get("cod", False)
        if status in by_status:
            by_status[status] += row["n"]
            if status in REVENUE_STATUS and not (cod and status == "shipped"):
                revenue += row["sum"]
                paid_orders += row["n"]
    return by_status, revenue, paid_orders


def today_summary(db):
    start = awal_hari_wib((utcnow() + WIB_OFFSET).date())
    revenue = 0
    paid_today = {"$or": [{"paid_at": {"$gte": start}},
                          {"paid_at": {"$exists": False}, "created_at": {"$gte": start}}]}
    pipeline = [{"$match": {**paid_today, "status": {"$in": list(REVENUE_STATUS)}, "$nor": [BELUM_DITERIMA]}},
                {"$group": {"_id": None, "sum": {"$sum": OMZET}}}]
    for row in db.orders.aggregate(pipeline):
        revenue = row["sum"]
    return {"orders": db.orders.count_documents({"created_at": {"$gte": start}}), "revenue": revenue}


def report_range(raw_from, raw_to):
    """Rentang laporan dalam tanggal WIB. Kosong berarti REPORT_DEFAULT_DAYS hari terakhir."""
    try:
        end = date.fromisoformat(raw_to) if raw_to else (utcnow() + WIB_OFFSET).date()
        start = date.fromisoformat(raw_from) if raw_from else end - timedelta(days=REPORT_DEFAULT_DAYS - 1)
    except ValueError:
        raise ApiError("Tanggal tidak valid. Gunakan format TTTT-BB-HH.", 422)
    if start > end:
        raise ApiError("Tanggal awal tidak boleh setelah tanggal akhir.", 422)
    if (end - start).days >= REPORT_MAX_DAYS:
        raise ApiError(f"Rentang laporan paling lama {REPORT_MAX_DAYS} hari.", 422)
    return start, end


def report_group(raw, days):
    if days > REPORT_DAILY_MAX_DAYS:
        return "month"
    return raw if raw in ("day", "month") else "day"


def build_report(orders, start, end, group):
    def bucket(day):
        return day.isoformat() if group == "day" else day.strftime("%Y-%m")

    series = {}
    day = start
    while day <= end:
        series.setdefault(bucket(day), {"revenue": 0, "orders": 0})
        day += timedelta(days=1)

    products = {}
    total = {"revenue": 0, "orders": 0, "items": 0, "shipping": 0}
    for order in orders:
        paid = order.get("paid_at") or order["created_at"]
        point = series.get(bucket((paid + WIB_OFFSET).date()))
        if point is None:
            continue
        amount = omzet_pesanan(order)
        point["revenue"] += amount
        point["orders"] += 1
        total["revenue"] += amount
        total["orders"] += 1
        total["shipping"] += order.get("shipping_fee") or 0
        for item in order.get("items", []):
            row = products.setdefault(str(item["product_id"]),
                                      {"product_id": str(item["product_id"]), "name": item["name"], "qty": 0, "revenue": 0})
            row["qty"] += item["qty"]
            row["revenue"] += item["subtotal"]
            total["items"] += item["qty"]

    top = sorted(products.values(), key=lambda p: (-p["qty"], -p["revenue"], p["name"]))[:TOP_PRODUCTS_SIZE]
    total["average"] = round(total["revenue"] / total["orders"]) if total["orders"] else 0
    return {"summary": total,
            "series": [{"key": key, **point} for key, point in series.items()],
            "top_products": top}


def sales_report(db, start, end, group):
    rentang = {"$gte": awal_hari_wib(start), "$lt": awal_hari_wib(end + timedelta(days=1))}
    # Tanggal yang dipakai tanggal bayar; pesanan lama tanpa paid_at memakai tanggal dibuat
    query = {"status": {"$in": list(REVENUE_STATUS)}, "$nor": [BELUM_DITERIMA],
             "$or": [{"paid_at": rentang}, {"paid_at": {"$exists": False}, "created_at": rentang}]}
    fields = {"paid_at": 1, "created_at": 1, "subtotal": 1, "total": 1, "shipping_fee": 1, "items": 1}
    return build_report(db.orders.find(query, fields), start, end, group)