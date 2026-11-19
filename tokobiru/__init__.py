"""Paket TokoBiru: application factory & namespace terpadu."""
import os
import smtplib
from datetime import timedelta

from flask import Flask

from tokobiru.ai.proof_reader import (  # noqa: F401
    ProofReadError,
    evaluate_proof,
    proof_fingerprint,
    read_transfer_proof,
)
from tokobiru.core import connection, passwords, security  # noqa: F401
from tokobiru.core.config import *  # noqa: F401,F403
from tokobiru.core.config import _env_int, _env_str  # noqa: F401
from tokobiru.core.connection import ensure_indexes, mongo_uri, ensure_ttl_index, migrate_legacy_collections, mongo_db_name  # noqa: F401
from tokobiru.core.util import format_rupiah, utcnow  # noqa: F401
from tokobiru.core.validation import Form, is_strong_password, parse_int, sanitize  # noqa: F401
from tokobiru.errors import ApiError, register_errors  # noqa: F401
from tokobiru.services.bootstrap import (  # noqa: F401
    DEMO_PASSWORD,
    DEMO_PRODUCTS,
    DEMO_USERS,
    bootstrap,
    seed_demo,
)
from tokobiru.services.mailer import reset_email_html, send_email  # noqa: F401
from tokobiru.services.notifications import push_staff  # noqa: F401
from tokobiru.services.orders.codes import new_order_code  # noqa: F401
from tokobiru.services.orders.expiry import sweep_expired_orders  # noqa: F401
from tokobiru.services.orders.idempotency import replayed_order  # noqa: F401
from tokobiru.services.payments.proof import read_with_fallback  # noqa: F401
from tokobiru.services.products import text_search_term  # noqa: F401
from tokobiru.services.users import new_user_doc, user_form  # noqa: F401

from tokobiru.routes import (
    addresses,
    auth,
    logs,
    orders,
    pages,
    password_reset,
    payments,
    products,
    push,
    stats,
    users,
)

BLUEPRINTS = (
    auth.bp,
    password_reset.bp,
    addresses.bp,
    products.bp,
    orders.bp,
    payments.bp,
    push.bp,
    users.bp,
    stats.bp,
    logs.bp,
    pages.bp,
)


def create_app():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    flask_app = Flask(
        __name__,
        static_folder=os.path.join(root_dir, "static"),
        template_folder=os.path.join(root_dir, "templates"),
    )
    flask_app.config.update(
        SECRET_KEY=SECRET_KEY,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=IS_VERCEL,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=MAX_PRODUCT_BODY_BYTES,
    )
    register_errors(flask_app)
    for bp in BLUEPRINTS:
        flask_app.register_blueprint(bp)
    connection.after_connect = bootstrap
    security.pasang(flask_app)
    return flask_app