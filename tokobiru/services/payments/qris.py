import re
from html import escape as html_escape

from flask import Response

from tokobiru.core.security import audit
from tokobiru.core.util import format_rupiah, utcnow
from tokobiru.services.notifications import CUSTOMER_PUSH, push_staff, push_user

PAY_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


QRIS_ACTOR = {"username": "qris", "role": "-"}


def mark_order_paid(db, order, via, actor=None):
    # Atomik: hanya pesanan yang masih pending yang bisa ditandai dibayar
    now = utcnow()
    result = db.orders.update_one(
        {"_id": order["_id"], "status": "pending"},
        {"$set": {"status": "paid", "paid_at": now, "paid_via": via, "updated_at": now}})
    if result.modified_count != 1:
        return False
    audit("pesanan_status", f"{order['code']}: pending → paid", actor)
    push_staff("Pembayaran masuk", f"{order['code']} · {format_rupiah(order['total'])} sudah dibayar. Siap diproses.",
               f"order-{order['code']}-bayar")
    title, body = CUSTOMER_PUSH["paid"](order["code"])
    push_user(order["user_id"], title, body, f"my-{order['code']}-paid")
    return True


def qris_page(ok, title, lines, status=200):
    color = "#07674c" if ok else "#b42318"
    shape = '<path d="M15 27l8 8 14-19"/>' if ok else '<path d="M18 18l16 16M34 18L18 34"/>'
    icon = (f'<svg viewBox="0 0 52 52" width="84" height="84" fill="none" stroke="{color}" stroke-width="3" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="26" cy="26" r="24"/>{shape}</svg>')
    body = "".join(f"<p>{html_escape(line)}</p>" for line in lines)
    page = ('<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html_escape(title)} - TokoBiru</title>'
            '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f7fc;color:#0c2342;'
            'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;padding:24px;box-sizing:border-box}'
            'main{background:#fff;border:1px solid #dce6f3;border-radius:20px;padding:32px 28px;max-width:360px;width:100%}'
            'h1{font-size:1.35rem;margin:14px 0 8px}p{margin:6px 0;color:#425d7a;line-height:1.45}'
            'small{display:block;margin-top:18px;color:#566f89;font-size:.8rem}</style></head>'
            f'<body><main>{icon}<h1>{html_escape(title)}</h1>{body}'
            '</main></body></html>')
    return Response(page, status=status, mimetype="text/html")