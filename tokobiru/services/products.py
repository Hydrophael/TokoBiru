from flask import current_app
import re
import time
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from tokobiru.core.config import PRODUCTS_LIMIT, PRODUCT_COLLECTION
from tokobiru.core.validation import Form, parse_int
from tokobiru.core.serializers import serialize
from tokobiru.errors import ApiError


def product_form(data):
    form = Form(data)
    form.text("name", "Nama produk", 2, 80)
    form.text("category", "Kategori", 2, 30)
    form.integer("price", "Harga", 100, 100_000_000)
    form.integer("stock", "Stok", 0, 100_000)
    form.text("description", "Deskripsi", 0, 300, required=False, multiline=True)
    form.image("image", "Foto produk")
    return form.done()


NO_IMAGE = {"image": 0}


def product_json(doc):
    out = serialize(doc)
    if doc.get("image_v"):
        out["photo"] = f"/api/products/{out['id']}/image?v={int(doc['image_v'])}"
    return out


def split_image(clean):
    if "image" not in clean:
        return {}, {}
    image = clean.pop("image")
    if image is None:
        return {}, {"image": "", "image_type": "", "image_v": ""}
    data, mime = image
    return {"image": data, "image_type": mime, "image_v": int(time.time() * 1000)}, {}


def text_search_term(search):
    words = (word.replace('"', "").replace("\\", "").lstrip("-") for word in search.split())
    return " ".join(word for word in words if word)


def search_products(db, search, category):
    collection = db[PRODUCT_COLLECTION]
    base = {"category": category} if category else {}
    term = text_search_term(search)
    if term:
        text_query = {**base, "$text": {"$search": term}}
        try:
            docs = list(collection.find(text_query, {"_score": {"$meta": "textScore"}, **NO_IMAGE})
                        .sort([("_score", {"$meta": "textScore"})]).limit(PRODUCTS_LIMIT))
        except OperationFailure as exc:
            current_app.logger.warning("Pencarian teks gagal, memakai regex: %s", exc)
            docs = []
        if docs:
            for doc in docs:
                doc.pop("_score", None)
            return docs, text_query
    regex_query = {**base, "name": {"$regex": re.escape(search), "$options": "i"}}
    docs = list(collection.find(regex_query, NO_IMAGE).sort("name", 1).limit(PRODUCTS_LIMIT))
    return docs, regex_query


def parse_base_stock(data):
    raw = data.get("base_stock")
    if raw is None or raw == "":
        return None
    value = parse_int(raw) if not isinstance(raw, bool) else None
    if value is None or not 0 <= value <= 100_000:
        raise ApiError("Periksa kembali isian Anda", 422, {"stock": "Stok awal tidak valid. Muat ulang halaman."})
    return value
