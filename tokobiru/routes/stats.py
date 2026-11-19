from flask import Blueprint, jsonify, request

from tokobiru.core.config import (
    LOW_STOCK_LIMIT,
    LOW_STOCK_LIST_SIZE,
    PRODUCT_COLLECTION,
    RECENT_ORDERS_SIZE,
    ROLES,
    STAFF_ROLES,
)
from tokobiru.core.connection import get_db
from tokobiru.core.security import current_user, roles_required
from tokobiru.core.serializers import serialize
from tokobiru.services.orders.expiry import sweep_expired_orders
from tokobiru.services.products import NO_IMAGE, product_json
from tokobiru.services.stats import order_summary, report_group, report_range, sales_report, today_summary

bp = Blueprint("stats", __name__)


@bp.get("/api/stats")
@roles_required(*STAFF_ROLES)
def stats():
    db = get_db()
    sweep_expired_orders(db)
    by_status, revenue, paid_orders = order_summary(db)
    low_stock = (db[PRODUCT_COLLECTION].find({"stock": {"$lte": LOW_STOCK_LIMIT}}, NO_IMAGE)
                 .sort("stock", 1).limit(LOW_STOCK_LIST_SIZE))
    recent = db.orders.find().sort("created_at", -1).limit(RECENT_ORDERS_SIZE)
    result = {
        "revenue": revenue,
        "paid_orders": paid_orders,
        "today": today_summary(db),
        "orders": {"total": sum(by_status.values()), **by_status},
        "products": db[PRODUCT_COLLECTION].count_documents({}),
        "low_stock": [product_json(p) for p in low_stock],
        "low_stock_total": db[PRODUCT_COLLECTION].count_documents({"stock": {"$lte": LOW_STOCK_LIMIT}}),
        "out_of_stock_total": db[PRODUCT_COLLECTION].count_documents({"stock": 0}),
        "recent": [serialize(o) for o in recent],
        "users": None,
    }
    if current_user()["role"] == "master":
        result["users"] = {role: db.users.count_documents({"role": role}) for role in ROLES}
    return jsonify(result)


@bp.get("/api/stats/sales")
@roles_required(*STAFF_ROLES)
def sales():
    start, end = report_range(request.args.get("from", ""), request.args.get("to", ""))
    days = (end - start).days + 1
    group = report_group(request.args.get("group", ""), days)
    report = sales_report(get_db(), start, end, group)
    return jsonify({"from": start.isoformat(), "to": end.isoformat(), "group": group, "days": days, **report})