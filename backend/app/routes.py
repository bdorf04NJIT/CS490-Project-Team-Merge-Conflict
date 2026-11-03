from flask import Blueprint, current_app, g, jsonify, request

from .auth import require_auth
from .services.ingestion import import_supplied_reviews, start_ingestion
from .services.review_storage import list_reviews
from .services.targets import create_target, get_target, list_targets, update_target

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


@bp.patch("/targets/<target_id>")
@require_auth
def patch_target(target_id):
    # Ownership is enforced inside update_target; the URL id alone grants nothing.
    target = update_target(
        current_app.extensions["database"],
        owner_id=g.user_id,
        target_id=target_id,
        payload=request.get_json(silent=True),
    )
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


@bp.post("/targets/<target_id>/ingestions/import")
@require_auth
def post_ingestion_import(target_id):
    # The import service verifies target ownership BEFORE it reads upload bytes.
    result = import_supplied_reviews(
        current_app.extensions["database"],
        owner_id=g.user_id,
        target_id=target_id,
        upload=lambda: request.files.get("file"),
    )
    return jsonify(run=result), 201


@bp.get("/targets/<target_id>/reviews")
@require_auth
def get_target_reviews(target_id):
    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        from .errors import ValidationError

        raise ValidationError("Invalid review offset.") from None
    if offset < 0 or offset > 100000:
        from .errors import ValidationError

        raise ValidationError("Invalid review offset.")
    rows = list_reviews(
        current_app.extensions["database"],
        owner_id=g.user_id,
        target_id=target_id,
        offset=offset,
    )
    return jsonify(reviews=rows)
