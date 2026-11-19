import secrets

from flask import Blueprint, jsonify

from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, current_user, roles_required
from tokobiru.core.validation import json_body
from tokobiru.errors import ApiError
from tokobiru.services.addresses import (
    ADDRESS_LIMIT,
    address_form,
    find_address,
    save_addresses,
)

bp = Blueprint("addresses", __name__)


@bp.post("/api/auth/addresses")
@roles_required("user")
def addresses_create():
    clean = address_form(json_body())
    db = get_db()
    user = current_user()
    addresses = list(user.get("addresses", []))
    if len(addresses) >= ADDRESS_LIMIT:
        raise ApiError(f"Maksimal {ADDRESS_LIMIT} alamat. Hapus salah satu dulu.", 409)
    first = not addresses
    if clean["main"] or first:
        for item in addresses:
            item["main"] = False
    addresses.append({"id": secrets.token_hex(6), "label": clean["label"], "recipient": clean["recipient"],
                      "phone": clean["phone"], "address": clean["address"], "main": clean["main"] or first})
    saved = save_addresses(db, user, addresses)
    audit("alamat_ubah", f"alamat {clean['label']} ditambah")
    return jsonify({"addresses": saved}), 201


@bp.put("/api/auth/addresses/<address_id>")
@roles_required("user")
def addresses_update(address_id):
    clean = address_form(json_body())
    db = get_db()
    user = current_user()
    addresses = list(user.get("addresses", []))
    target = find_address(addresses, address_id)
    if clean["main"]:
        for item in addresses:
            item["main"] = False
    target.update({"label": clean["label"], "recipient": clean["recipient"], "phone": clean["phone"],
                   "address": clean["address"], "main": clean["main"] or bool(target.get("main"))})
    saved = save_addresses(db, user, addresses)
    audit("alamat_ubah", f"alamat {clean['label']} diubah")
    return jsonify({"addresses": saved})


@bp.delete("/api/auth/addresses/<address_id>")
@roles_required("user")
def addresses_delete(address_id):
    db = get_db()
    user = current_user()
    addresses = list(user.get("addresses", []))
    target = find_address(addresses, address_id)
    addresses = [item for item in addresses if item is not target]
    if target.get("main") and addresses:
        addresses[0]["main"] = True
    saved = save_addresses(db, user, addresses)
    audit("alamat_ubah", f"alamat {target['label']} dihapus")
    return jsonify({"addresses": saved})