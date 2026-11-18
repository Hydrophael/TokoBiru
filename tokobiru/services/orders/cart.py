from bson import ObjectId

from tokobiru.core.config import MAX_CART_LINES, MAX_QTY_PER_PRODUCT
from tokobiru.core.validation import Form, object_id
from tokobiru.errors import ApiError


def parse_cart_items(items):
    if not isinstance(items, list) or not items or len(items) > MAX_CART_LINES:
        raise ApiError("Keranjang kosong atau terlalu banyak item", 422)
    wanted = {}
    for item in items:
        if not isinstance(item, dict):
            raise ApiError("Item keranjang tidak valid", 422)
        product_id = object_id(item.get("product_id"), "Produk")
        form = Form(item)
        form.integer("qty", "Jumlah", 1, MAX_QTY_PER_PRODUCT)
        wanted[product_id] = wanted.get(product_id, 0) + form.done()["qty"]
    if any(qty > MAX_QTY_PER_PRODUCT for qty in wanted.values()):
        raise ApiError(f"Maksimal {MAX_QTY_PER_PRODUCT} unit per produk", 422)
    return wanted


def parse_expected_prices(items):
    expected = {}
    for item in items:
        if item.get("price") is None:
            continue
        form = Form(item)
        form.integer("price", "Harga", 1, 100_000_000)
        expected[ObjectId(item["product_id"])] = form.done()["price"]
    return expected