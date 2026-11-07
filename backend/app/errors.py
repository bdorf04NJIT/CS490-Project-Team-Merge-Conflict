from flask import jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status = 500
    code = "INTERNAL_ERROR"
    message = "Something went wrong."

    def __init__(self, message=None, fields=None):
        super().__init__(message or self.message)
        if message:
            self.message = message
        self.fields = fields or {}


class Unauthenticated(AppError):
    status = 401
    code = "UNAUTHENTICATED"
    message = "Please sign in to continue."


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"
    message = "Not found."


class ValidationError(AppError):
    status = 400
    code = "VALIDATION_ERROR"
    message = "Provide only name, platform, and a valid HTTP(S) source_url. Ownership is assigned automatically."


class IngestionUnavailable(AppError):
    status = 503
    code = "INGESTION_UNAVAILABLE"
    message = "Review ingestion isn't available right now. Please try again later."


class IngestionFailed(AppError):
    status = 422
    code = "INGESTION_FAILED"
    message = "No usable review data could be imported."


class QaUnavailable(AppError):
    status = 503
    code = "QA_UNAVAILABLE"
    message = "The review assistant isn't available right now. Please try again in a moment."


def _body(code, message, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return jsonify(error=error)


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(e):
        return _body(e.code, e.message, e.fields), e.status

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        if isinstance(e, HTTPException):
            return _body("HTTP_ERROR", e.name), e.code
        app.logger.exception("Unexpected error")
        return _body("INTERNAL_ERROR", "Something went wrong."), 500
