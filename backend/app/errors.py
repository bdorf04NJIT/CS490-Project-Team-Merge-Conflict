from flask import jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status = 500
    code = "INTERNAL_ERROR"
    message = "Something went wrong."


class Unauthenticated(AppError):
    status = 401
    code = "UNAUTHENTICATED"
    message = "Please sign in to continue."


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"
    message = "Not found."


def _body(code, message):
    return jsonify(error={"code": code, "message": message})


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(e):
        return _body(e.code, e.message), e.status

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        if isinstance(e, HTTPException):
            return _body("HTTP_ERROR", e.name), e.code
        app.logger.exception("Unexpected error")
        return _body("INTERNAL_ERROR", "Something went wrong."), 500
