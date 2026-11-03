from flask import Blueprint, current_app, g, jsonify, request

from .auth import require_auth
from .services.ingestion import start_ingestion
from .services.targets import create_target, get_target, list_targets

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
        current_app.extensions["database"],
        owner_id=g.user_id,
        payload=request.get_json(silent=True),
    )
    return jsonify(target), 201


@bp.get("/targets")
@require_auth
def get_targets():
    # Ownership comes only from the verified token. Query params are never read.
    targets = list_targets(current_app.extensions["database"], owner_id=g.user_id)
    return jsonify(targets=targets)


@bp.get("/targets/<target_id>")
@require_auth
def get_one_target(target_id):
    # The URL id only says which target is requested; ownership is checked in the query.
    target = get_target(current_app.extensions["database"], owner_id=g.user_id, target_id=target_id)
    return jsonify(target)


@bp.post("/targets/<target_id>/ingestions")
@require_auth
def post_ingestion(target_id):
    # Ownership, body, and source checks all run before the review source is called.
    result = start_ingestion(
        current_app.extensions["database"],
        current_app.extensions["review_source"],
        owner_id=g.user_id,
        target_id=target_id,
        payload=request.get_json(silent=True),
    )
    return jsonify(result), 202
