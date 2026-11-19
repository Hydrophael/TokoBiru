from flask import Blueprint, jsonify

from tokobiru.core.config import LOGS_LIMIT, WIB_OFFSET
from tokobiru.core.connection import get_db
from tokobiru.core.security import audit, roles_required
from tokobiru.core.serializers import serialize
from tokobiru.core.validation import json_body, object_id
from tokobiru.errors import ApiError

bp = Blueprint("logs", __name__)


@bp.get("/api/logs")
@roles_required("master")
def logs_list():
    docs = get_db().logs.find().sort("ts", -1).limit(LOGS_LIMIT)
    return jsonify({"logs": [serialize(log) for log in docs]})


@bp.post("/api/logs/delete")
@roles_required("master")
def logs_delete():
    ids = json_body().get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= LOGS_LIMIT:
        raise ApiError(f"Pilih 1 sampai {LOGS_LIMIT} log", 422)
    oids = list({object_id(item, "Log") for item in ids})
    db = get_db()
    # Ringkasan dicatat sebelum dihapus; isi log yang dihapus tidak disimpan, hanya berapa banyak dan rentang waktunya
    doomed = list(db.logs.find({"_id": {"$in": oids}}, {"ts": 1}))
    result = db.logs.delete_many({"_id": {"$in": oids}})
    if result.deleted_count:
        stamps = sorted(doc["ts"] for doc in doomed if doc.get("ts"))
        span = (f", {(stamps[0] + WIB_OFFSET).strftime('%d/%m/%y %H:%M')} s/d {(stamps[-1] + WIB_OFFSET).strftime('%d/%m/%y %H:%M')} WIB"
                if stamps else "")
        audit("log_hapus", f"{result.deleted_count} log dihapus{span}")
    return jsonify({"deleted": result.deleted_count})