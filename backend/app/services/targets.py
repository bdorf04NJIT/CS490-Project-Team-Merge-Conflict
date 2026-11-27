import re
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import NotFound, ValidationError
from ..models import AnalysisTarget, IngestionRun, Review
from .review_storage import count_reviews, latest_run

PLATFORM = "google_maps"

ALLOWED_FIELDS = {"name", "platform", "source_url"}
MAX_NAME = 255
MAX_URL = 2048

# google.com, google.co.uk, google.com.au, ... (optionally with www. or maps.)
_GOOGLE_DOMAIN = r"google\.(?:com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})"
_GOOGLE_HOST = re.compile(rf"^(?:www\.)?{_GOOGLE_DOMAIN}$")
_MAPS_HOST = re.compile(rf"^maps\.{_GOOGLE_DOMAIN}$")

MESSAGES = {
    "name_missing": "Enter the business or place name.",
    "name_long": f"The name must be {MAX_NAME} characters or fewer.",
    "url_missing": "Enter the Google Maps URL for this place.",
    "url_invalid": "Enter a complete URL starting with https://.",
    "url_long": f"The URL must be {MAX_URL} characters or fewer.",
    "url_not_maps": "Enter a Google Maps link, such as https://www.google.com/maps/place/... "
    "or https://maps.app.goo.gl/...",
    "platform": "Google Maps is the only supported review platform.",
}


def is_google_maps_url(url):
    host = (url.hostname or "").lower()
    path = url.path.lower()
    if _GOOGLE_HOST.match(host):
        return path == "/maps" or path.startswith("/maps/")
    if _MAPS_HOST.match(host):
        return True
    if host == "maps.app.goo.gl":
        return path.strip("/") != ""
    if host == "goo.gl":
        return path.startswith("/maps/") and path != "/maps/"
    return False


def source_url_error(source_url):
    """Return a user-facing message if source_url is not a usable Google Maps URL."""
    if not source_url:
        return MESSAGES["url_missing"]
    if len(source_url) > MAX_URL:
        return MESSAGES["url_long"]
    try:
        url = urlsplit(source_url)
        usable = (
            url.scheme in {"http", "https"}
            and bool(url.hostname)
            and not url.username
            and not url.password
            and " " not in source_url
        )
        _ = url.port  # invalid port numbers raise ValueError
    except ValueError:
        usable = False
    if not usable:
        return MESSAGES["url_invalid"]
    if not is_google_maps_url(url):
        return MESSAGES["url_not_maps"]
    return None


def _text(payload, field):
    value = payload.get(field)
    return value.strip() if isinstance(value, str) else ""


def validate_target(payload):
    # An allowlist rejects ownership aliases (userId, owner_id, ...) and mass assignment.
    if not isinstance(payload, dict) or not set(payload) <= ALLOWED_FIELDS:
        raise ValidationError()

    errors = {}
    name = _text(payload, "name")
    if not name:
        errors["name"] = MESSAGES["name_missing"]
    elif len(name) > MAX_NAME:
        errors["name"] = MESSAGES["name_long"]

    source_url = _text(payload, "source_url")
    url_error = source_url_error(source_url)
    if url_error:
        errors["source_url"] = url_error

    if payload.get("platform") != PLATFORM:
        errors["platform"] = MESSAGES["platform"]

    if errors:
        raise ValidationError("Some target details need fixing.", fields=errors)
    return {"name": name, "platform": PLATFORM, "source_url": source_url}


def _summary(row):
    # owner_id is intentionally omitted: the caller already knows it from the token.
    return {
        "id": row.id,
        "name": row.name,
        "platform": row.platform,
        "source_url": row.source_url,
        "created_at": row.created_at.isoformat(),
    }


def list_targets(engine, *, owner_id):
    """Return only the targets owned by owner_id, newest first.

    The ownership filter is applied in the database query, never in the caller.
    """
    with Session(engine) as session:
        rows = session.scalars(
            select(AnalysisTarget)
            .where(AnalysisTarget.owner_id == owner_id)
            .order_by(AnalysisTarget.created_at.desc(), AnalysisTarget.id)
        ).all()
        return [_summary(row) for row in rows]


def find_owned_target(session, *, owner_id, target_id):
    """Load a target by id and owner in one query, or raise NotFound.

    Another user's target and a target that does not exist raise the same
    NotFound, so a caller cannot learn whether someone else's id exists.
    """
    row = session.scalars(
        select(AnalysisTarget).where(
            AnalysisTarget.id == target_id, AnalysisTarget.owner_id == owner_id
        )
    ).one_or_none()
    if row is None:
        raise NotFound("We couldn't find that analysis target.")
    return row


def get_target(engine, *, owner_id, target_id):
    """Return one target only if owner_id owns it (see find_owned_target)."""
    with Session(engine) as session:
        row = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        return {
            **_summary(row),
            "latest_ingestion": latest_run(engine, owner_id=owner_id, target_id=target_id),
            # S3-009: lets the workspace offer "Refresh reviews" once a dataset exists.
            "review_count": count_reviews(engine, owner_id=owner_id, target_id=target_id),
        }


def create_target(engine, *, owner_id, payload):
    values = validate_target(payload)
    with Session(engine) as session, session.begin():
        target = AnalysisTarget(owner_id=owner_id, **values)
        session.add(target)
        session.flush()
        result = {
            "id": target.id,
            "owner_id": target.owner_id,
            "name": target.name,
            "platform": target.platform,
            "source_url": target.source_url,
            "created_at": target.created_at.isoformat(),
        }
    return result


UPDATABLE_FIELDS = {"name", "source_url"}


def validate_target_update(payload):
    # Only name and source_url may change. Ownership, id, and platform are never client-editable.
    if not isinstance(payload, dict) or not payload or not set(payload) <= UPDATABLE_FIELDS:
        raise ValidationError("Provide only name and/or source_url to update.")
    errors, values = {}, {}
    if "name" in payload:
        name = _text(payload, "name")
        if not name:
            errors["name"] = MESSAGES["name_missing"]
        elif len(name) > MAX_NAME:
            errors["name"] = MESSAGES["name_long"]
        values["name"] = name
    if "source_url" in payload:
        source_url = _text(payload, "source_url")
        url_error = source_url_error(source_url)
        if url_error:
            errors["source_url"] = url_error
        values["source_url"] = source_url
    if errors:
        raise ValidationError("Some target details need fixing.", fields=errors)
    return values


def update_target(engine, *, owner_id, target_id, payload):
    """Update a target only if owner_id owns it.

    Ownership is checked BEFORE the body is validated, so a non-owner always gets
    the same NotFound as a missing id and learns nothing from validation errors.
    """
    with Session(engine) as session, session.begin():
        row = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        for field, value in validate_target_update(payload).items():
            setattr(row, field, value)
        session.flush()
        return _summary(row)


# S3-003: fields of a Review that are part of the "current saved state" we copy.
# id, target_id, and ingestion_run_id are deliberately omitted: the copy gets its
# own identity, its own target, and its own ingestion run (new rows, not shared).
_REVIEW_COPY_FIELDS = (
    "text",
    "rating",
    "source_review_id",
    "reviewer_name",
    "review_date",
    "review_url",
    "source_name",
)


def validate_new_name(name):
    """Validate a human-readable analysis name, as used by Save As (S3-003)."""
    value = name.strip() if isinstance(name, str) else ""
    if not value:
        raise ValidationError(
            "Some target details need fixing.", fields={"name": MESSAGES["name_missing"]}
        )
    if len(value) > MAX_NAME:
        raise ValidationError(
            "Some target details need fixing.", fields={"name": MESSAGES["name_long"]}
        )
    return value


def save_as_target(engine, *, owner_id, target_id, name):
    """Create a separate analysis from an owned source analysis (S3-003).

    The copy receives a new identity and begins with the source's current persisted
    review dataset. Reviews are copied as new rows anchored to a fresh ingestion run
    on the copy, so the copy is fully independent of the source: renaming, deleting,
    or re-ingesting it never touches the original. Q&A history is not persisted yet
    (S3-006), so there is nothing to copy; this will be revisited when it exists.
    """
    new_name = validate_new_name(name)
    with Session(engine) as session, session.begin():
        source = find_owned_target(session, owner_id=owner_id, target_id=target_id)

        copy = AnalysisTarget(
            owner_id=owner_id,
            name=new_name,
            platform=source.platform,
            source_url=source.source_url,
        )
        session.add(copy)
        session.flush()

        source_reviews = session.scalars(select(Review).where(Review.target_id == source.id)).all()

        if source_reviews:
            run = IngestionRun(
                target_id=copy.id,
                source_kind=source.platform,
                status="succeeded",
                total_count=len(source_reviews),
                imported_count=len(source_reviews),
                skipped_count=0,
                message="Copied from the source analysis.",
            )
            session.add(run)
            session.flush()
            for review in source_reviews:
                session.add(
                    Review(
                        target_id=copy.id,
                        ingestion_run_id=run.id,
                        **{field: getattr(review, field) for field in _REVIEW_COPY_FIELDS},
                    )
                )
            session.flush()

        return _summary(copy)
