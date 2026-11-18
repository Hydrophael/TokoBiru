"""TokoBiru - galat yang dilempar kode bisnis; error handler di app.py mengubahnya menjadi respons JSON."""


class ApiError(Exception):
    def __init__(self, message, status=400, fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.fields = fields or {}
