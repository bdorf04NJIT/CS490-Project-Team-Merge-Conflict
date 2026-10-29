from flask import Blueprint, current_app, g, jsonify, request

from .auth import require_auth
from .services.targets import create_target

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify(status="ok")


@bp.get("/me")
@require_auth
def me():
    return jsonify(user_id=g.user_id)


@bp.post("/targets")
@require_auth
def post_target():
    target = create_target(
        current_app.extensions["database"], owner_id=g.user_id,
        payload=request.get_json(silent=True),
    )
    return jsonify(target), 201
