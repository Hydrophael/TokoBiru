from flask import Blueprint, Response, current_app, g, has_request_context, jsonify, request, send_from_directory, session
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument, UpdateOne
from tokobiru.core.config import PRODUCTS_LIMIT, PRODUCT_COLLECTION, STAFF_ROLES
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, login_required, roles_required
from tokobiru.core.validation import json_body, object_id, sanitize
from tokobiru.core.util import format_rupiah, utcnow
from tokobiru.errors import ApiError
from tokobiru.services.orders.expiry import sweep_expired_orders
from tokobiru.services.products import NO_IMAGE, parse_base_stock, product_form, product_json, search_products, split_image

bp = Blueprint("products", __name__)


@bp.get("/api/products")
@login_required
def products_list():
    db = get_db()
    sweep_expired_orders(db)
    search = sanitize(str(request.args.get("q", ""))[:50])
    category = sanitize(str(request.args.get("category", ""))[:30])
    if search:
        docs, query = search_products(db, search, category)
    else:
        query = {"category": category} if category else {}
        docs = list(db[PRODUCT_COLLECTION].find(query, NO_IMAGE).sort("name", 1).limit(PRODUCTS_LIMIT))
    categories = sorted(c for c in db[PRODUCT_COLLECTION].distinct("category") if isinstance(c, str))
    return jsonify({"products": [product_json(p) for p in docs], "categories": categories,
                    "total": db[PRODUCT_COLLECTION].count_documents(query)})


@bp.post("/api/products")
@roles_required(*STAFF_ROLES)
def products_create():
    clean = product_form(json_body())
    image_set, _ = split_image(clean)
    clean.update(image_set)
    clean["created_at"] = clean["updated_at"] = utcnow()
    db = get_db()
    result = db[PRODUCT_COLLECTION].insert_one(clean)
    audit("produk_tambah", clean["name"] + (" (dengan foto)" if image_set else ""))
    created = db[PRODUCT_COLLECTION].find_one({"_id": result.inserted_id}, NO_IMAGE)
    return jsonify({"product": product_json(created)}), 201


@bp.put("/api/products/<product_id>")
@roles_required(*STAFF_ROLES)
def products_update(product_id):
    target_id = object_id(product_id, "Produk")
    body = json_body()
    clean = product_form(body)
    image_set, image_unset = split_image(clean)
    clean.update(image_set)
    base_stock = parse_base_stock(body)
    clean["updated_at"] = utcnow()
    db = get_db()
    collection = db[PRODUCT_COLLECTION]

    query = {"_id": target_id}
    new_stock = clean.pop("stock")
    update = {"$set": clean}
    if image_unset:
        update["$unset"] = image_unset
    delta = None
    if base_stock is None:
        clean["stock"] = new_stock
    else:
        delta = new_stock - base_stock
        if delta:
            update["$inc"] = {"stock": delta}
        if delta < 0:
            query["stock"] = {"$gte": -delta}

    # Dokumen sebelum diubah dibawa pulang oleh perintah yang sama, jadi harga lama yang dicatat pasti harga yang tergantikan
    before = collection.find_one_and_update(query, update, projection={"price": 1}, return_document=ReturnDocument.BEFORE)
    if before is None:
        if not collection.find_one({"_id": target_id}):
            raise ApiError("Produk tidak ditemukan", 404)
        raise ApiError("Stok berubah karena ada penjualan. Muat ulang halaman lalu coba lagi.", 409)
    old_price, new_price = before.get("price"), clean.get("price")
    price_note = (f" (harga {format_rupiah(old_price)} → {format_rupiah(new_price)})"
                  if isinstance(old_price, int) and isinstance(new_price, int) and old_price != new_price else "")
    photo_note = " (foto diganti)" if image_set else " (foto dihapus)" if image_unset else ""
    audit("produk_ubah", clean["name"] + (f" (stok {delta:+d})" if delta else "") + price_note + photo_note)
    return jsonify({"product": product_json(collection.find_one({"_id": target_id}, NO_IMAGE))})


@bp.get("/api/products/<product_id>/image")
@login_required
def products_image(product_id):
    target_id = object_id(product_id, "Produk")
    doc = get_db()[PRODUCT_COLLECTION].find_one({"_id": target_id}, {"image": 1, "image_type": 1})
    if not doc or not doc.get("image"):
        raise ApiError("Foto tidak ditemukan", 404)
    resp = Response(bytes(doc["image"]), mimetype=doc.get("image_type") or "image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


@bp.delete("/api/products/<product_id>")
@roles_required(*STAFF_ROLES)
def products_delete(product_id):
    target_id = object_id(product_id, "Produk")
    product = get_db()[PRODUCT_COLLECTION].find_one_and_delete({"_id": target_id})
    if not product:
        raise ApiError("Produk tidak ditemukan", 404)
    audit("produk_hapus", product["name"])
    return jsonify({"ok": True})
