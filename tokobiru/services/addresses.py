import re
from tokobiru.core.validation import Form, NAME_ERROR, PERSON_RE, PHONE_ERROR, PHONE_RE
from tokobiru.core.serializers import address_json
from tokobiru.errors import ApiError


ADDRESS_LIMIT = 5


ADDRESS_LABELS = ("Rumah", "Kantor", "Kos", "Lainnya")


def address_form(data):
    data = dict(data)
    if isinstance(data.get("phone"), str):
        data["phone"] = re.sub(r"[\s.\-]", "", data["phone"])
    form = Form(data)
    form.choice("label", "Label alamat", ADDRESS_LABELS)
    form.text("recipient", "Nama penerima", 2, 50, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.text("phone", "Nomor HP", 8, 16, regex=PHONE_RE, regex_msg=PHONE_ERROR)
    form.text("address", "Alamat pengiriman", 5, 200, multiline=True)
    clean = form.done()
    clean["main"] = data.get("main") is True
    return clean


def save_addresses(db, user, addresses):
    if addresses and not any(item.get("main") for item in addresses):
        addresses[0]["main"] = True
    db.users.update_one({"_id": user["_id"]}, {"$set": {"addresses": addresses}})
    return [address_json(item) for item in addresses]


def find_address(addresses, address_id):
    for item in addresses:
        if item["id"] == address_id:
            return item
    raise ApiError("Alamat tidak ditemukan", 404)
