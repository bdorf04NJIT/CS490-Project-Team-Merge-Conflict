from flask import Blueprint, g, jsonify

from .auth import require_auth

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/me")
@require_auth
def me():
    return jsonify(user_id=g.user_id)
