from flask import Blueprint, Response, current_app, g, has_request_context, jsonify, request, send_from_directory, session
from tokobiru.core.config import TEMPLATE_DIR
from tokobiru.core.connection import get_db

bp = Blueprint("pages", __name__)


@bp.get("/api/health")
def health():
    get_db().command("ping")
    return jsonify({"status": "ok"})


@bp.get("/")
def index():
    return send_from_directory(TEMPLATE_DIR, "index.html", mimetype="text/html")


@bp.get("/sw.js")
def service_worker():
    resp = send_from_directory(current_app.static_folder, "sw.js", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp
