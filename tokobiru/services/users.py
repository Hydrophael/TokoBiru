from tokobiru.core import passwords
from tokobiru.core.config import ASSIGNABLE_ROLES, VAPID_PUBLIC_KEY
from tokobiru.core.validation import EMAIL_ERROR, EMAIL_RE, Form, NAME_ERROR, PERSON_RE, USERNAME_ERROR, USERNAME_RE
from tokobiru.core.serializers import address_json, serialize
from tokobiru.core.util import utcnow
from tokobiru.services.notifications import PUSH_ENABLED


def public_user(user):
    if not user:
        return None
    out = {"id": str(user["_id"]), "username": user["username"], "name": user["name"],
           "email": user["email"], "role": user["role"]}
    if user.get("image_v"):
        out["photo"] = f"/api/auth/avatar?v={int(user['image_v'])}"
    if user["role"] == "user":
        out["addresses"] = [address_json(item) for item in user.get("addresses", [])]
    if PUSH_ENABLED:
        out["push_key"] = VAPID_PUBLIC_KEY   # admin, master, dan pelanggan boleh berlangganan notifikasi
    return out


def user_form(data, with_role=False):
    form = Form(data)
    form.text("name", "Nama lengkap", 2, 50, regex=PERSON_RE, regex_msg=NAME_ERROR)
    form.text("username", "Username", 3, 20, lower=True, regex=USERNAME_RE,
              regex_msg=USERNAME_ERROR)
    form.text("email", "Email", 5, 120, lower=True, regex=EMAIL_RE, regex_msg=EMAIL_ERROR)
    form.password()
    if with_role:
        form.choice("role", "Role", ASSIGNABLE_ROLES)
    return form.done()


def new_user_doc(fields, role):
    return {
        "name": fields["name"],
        "username": fields["username"],
        "email": fields["email"],
        "password_hash": passwords.hash_password(fields["password"]),
        "role": role,
        "active": True,
        "created_at": utcnow(),
        "failed": 0,
    }


def user_listing(doc):
    out = serialize(doc)
    if doc.get("image_v"):
        out["photo"] = f"/api/users/{out['id']}/avatar?v={int(doc['image_v'])}"
    return out


def forget_user_devices(db, user_id, notifications=False):
    """Lepas perangkat push akun ini; notifikasi dalam aplikasi ikut dihapus bila `notifications` (kabar staf tidak boleh tersisa)."""
    db.push_subs.delete_many({"user_id": user_id})
    if notifications:
        db.notifications.delete_many({"user_id": user_id})
