from tokobiru.core.config import ORDER_STATUS, REVENUE_STATUS, WIB_OFFSET
from tokobiru.core.util import utcnow


def order_summary(db):
    by_status = {status: 0 for status in ORDER_STATUS}
    revenue = paid_orders = 0
    pipeline = [{"$group": {"_id": {"status": "$status", "cod": {"$eq": ["$cod", True]}},
                            "n": {"$sum": 1}, "sum": {"$sum": "$total"}}}]
    for row in db.orders.aggregate(pipeline):
        status, cod = row["_id"]["status"], row["_id"].get("cod", False)
        if status in by_status:
            by_status[status] += row["n"]
            # COD yang masih dikirim belum dihitung: uangnya baru diterima saat selesai
            if status in REVENUE_STATUS and not (cod and status == "shipped"):
                revenue += row["sum"]
                paid_orders += row["n"]
    return by_status, revenue, paid_orders


def today_summary(db):
    local_now = utcnow() + WIB_OFFSET
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - WIB_OFFSET
    revenue = 0
    paid_today = {"$or": [{"paid_at": {"$gte": start}},
                          {"paid_at": {"$exists": False}, "created_at": {"$gte": start}}]}
    pipeline = [{"$match": {**paid_today, "status": {"$in": list(REVENUE_STATUS)},
                            "$nor": [{"cod": True, "status": "shipped"}]}},
                {"$group": {"_id": None, "sum": {"$sum": "$total"}}}]
    for row in db.orders.aggregate(pipeline):
        revenue = row["sum"]
    return {"orders": db.orders.count_documents({"created_at": {"$gte": start}}), "revenue": revenue}