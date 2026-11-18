from tokobiru.core.config import PRODUCT_COLLECTION
from tokobiru.core.util import format_rupiah
from tokobiru.errors import ApiError
from tokobiru.services.products import NO_IMAGE


def release_stock(db, reserved):
    for product_id, qty in reserved:
        db[PRODUCT_COLLECTION].update_one({"_id": product_id}, {"$inc": {"stock": qty}})


def reserve_stock(db, wanted, expected_prices=None):
    # Stok dikurangi atomik dan hanya berhasil bila cukup, jadi tidak bisa terjual melebihi stok
    reserved, lines = [], []
    try:
        for product_id, qty in wanted.items():
            product = db[PRODUCT_COLLECTION].find_one({"_id": product_id}, NO_IMAGE)
            if not product:
                raise ApiError("Ada produk yang sudah tidak tersedia", 404)
            seen_price = (expected_prices or {}).get(product_id)
            if seen_price is not None and seen_price != product["price"]:
                raise ApiError(
                    f"Harga '{product['name']}' berubah dari {format_rupiah(seen_price)} menjadi "
                    f"{format_rupiah(product['price'])}. Keranjang sudah diperbarui, periksa lagi sebelum memesan.",
                    409)
            result = db[PRODUCT_COLLECTION].update_one(
                {"_id": product_id, "stock": {"$gte": qty}}, {"$inc": {"stock": -qty}})
            if result.modified_count != 1:
                raise ApiError(f"Stok '{product['name']}' tidak mencukupi (tersisa {product['stock']})", 409)
            reserved.append((product_id, qty))
            lines.append({"product_id": product_id, "name": product["name"],
                          "price": product["price"], "qty": qty,
                          "subtotal": product["price"] * qty})
    except Exception:
        release_stock(db, reserved)
        raise
    return reserved, lines
