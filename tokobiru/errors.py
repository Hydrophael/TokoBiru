from flask import current_app
"""TokoBiru - galat yang dilempar kode bisnis; error handler di app.py mengubahnya menjadi respons JSON."""


class ApiError(Exception):
    def __init__(self, message, status=400, fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.fields = fields or {}

from flask import jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.exceptions import HTTPException


def register_errors(app):
    @app.errorhandler(ApiError)
    def handle_api_error(e):
        payload = {"error": e.message}
        if e.fields:
            payload["fields"] = e.fields
        return jsonify(payload), e.status


    @app.errorhandler(PyMongoError)
    def handle_mongo_error(e):
        current_app.logger.error("MongoDB error: %s", e)
        return jsonify({"error": "Database tidak dapat diakses. Coba lagi sebentar."}), 503


    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Endpoint tidak ditemukan"}), 404
        return Response("Halaman tidak ditemukan", status=404, mimetype="text/plain")


    @app.errorhandler(405)
    def handle_405(e):
        return jsonify({"error": "Metode tidak diizinkan"}), 405


    @app.errorhandler(413)
    def handle_413(e):
        return jsonify({"error": "Data yang dikirim terlalu besar"}), 413


    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code
        current_app.logger.exception("Unhandled error")
        return jsonify({"error": "Terjadi kesalahan pada server"}), 500
