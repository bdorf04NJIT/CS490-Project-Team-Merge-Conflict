"""Review-source orchestration, validation, normalization, and run reporting."""

import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from ..adapters.review_source_csv import MAX_CSV_BYTES, SourceFormatError, parse_review_csv
from ..adapters.serpapi_source import SerpApiGoogleMapsSource
from ..adapters.short_maps_links import ShortMapsLinkError, resolve_short_maps_link
from ..errors import IngestionFailed, IngestionUnavailable, ValidationError
from .review_normalization import normalize_reviews
from .review_storage import persist_reviews, record_failed_run
from .targets import find_owned_target, source_url_error

logger = logging.getLogger(__name__)

SOURCE_MESSAGE = "This target needs a valid Google Maps URL before reviews can be ingested."


def _ensure_owner(engine, owner_id, target_id):
    with Session(engine) as session:
        target = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        return target.source_url


def _complete_batch(engine, *, owner_id, target_id, batch):
    normalized = normalize_reviews(batch.rows)
    if not normalized.reviews:
        message = "No usable written reviews with ratings from 1 to 5 were found."
        record_failed_run(
            engine,
            owner_id=owner_id,
            target_id=target_id,
            source_kind=batch.source_kind,
            message=message,
            total_count=normalized.total_count,
            skipped_count=normalized.skipped_count,
            skip_reasons=normalized.skip_reasons,
        )
        raise IngestionFailed(message)
    run = persist_reviews(
        engine,
        owner_id=owner_id,
        target_id=target_id,
        source_kind=batch.source_kind,
        reviews=[asdict(review) for review in normalized.reviews],
        skipped_count=normalized.skipped_count,
        skip_reasons=normalized.skip_reasons,
    )
    return run


def start_ingestion(engine, review_source, *, owner_id, target_id, payload):
    """Preserve S1-019's owned empty-body request and source adapter contract.

    The legacy fake adapter returns None; that preserves its existing S1-019
    acceptance test. Real adapters return a RawReviewBatch and persist it here.
    """
    source_url = _ensure_owner(engine, owner_id, target_id)
    if payload not in (None, {}):
        raise ValidationError(
            "Ingestion uses the target's saved source. Send an empty request body."
        )
    if source_url_error((source_url or "").strip()):
        raise ValidationError(SOURCE_MESSAGE, fields={"source_url": SOURCE_MESSAGE})

    logger.info("Starting ingestion for target %s", target_id)
    try:
        # Only the real SerpAPI source needs a stable place identifier.
        # Fake/test and unconfigured sources preserve their existing contract.
        if isinstance(review_source, SerpApiGoogleMapsSource):
            try:
                source_url = resolve_short_maps_link(source_url)
            except ShortMapsLinkError as exc:
                raise ValidationError(str(exc)) from None
        batch = review_source.submit(target_id=target_id, source_url=source_url)
    except (IngestionUnavailable, ValidationError) as exc:
        # Store a safe, user-facing error; provider keys and stack traces never enter DB.
        record_failed_run(
            engine,
            owner_id=owner_id,
            target_id=target_id,
            source_kind="serpapi_google_maps",
            message=str(exc),
        )
        raise
    if batch is None:
        return {"target_id": target_id, "status": "accepted"}
    run = _complete_batch(engine, owner_id=owner_id, target_id=target_id, batch=batch)
    return {
        "target_id": target_id,
        "status": "accepted",
        "run_status": run["status"],
        "imported_count": run["imported_count"],
        "skipped_count": run["skipped_count"],
        "skip_reasons": run["skip_reasons"],
    }


def import_supplied_reviews(engine, *, owner_id, target_id, upload):
    """Authenticating and owning the target must precede reading uploaded bytes."""
    _ensure_owner(engine, owner_id, target_id)
    upload = upload() if callable(upload) else upload
    if upload is None or not upload.filename:
        raise ValidationError("Select a real Google Maps review CSV to import.")
    try:
        data = upload.stream.read(MAX_CSV_BYTES + 1)
        batch = parse_review_csv(data)
    except (SourceFormatError, OSError) as exc:
        message = str(exc) if isinstance(exc, SourceFormatError) else "The CSV could not be read."
        record_failed_run(
            engine,
            owner_id=owner_id,
            target_id=target_id,
            source_kind="google_maps_csv",
            message=message,
        )
        raise IngestionFailed(message) from None
    return _complete_batch(engine, owner_id=owner_id, target_id=target_id, batch=batch)
