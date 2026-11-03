import logging

from sqlalchemy.orm import Session

from ..errors import ValidationError
from .targets import find_owned_target, source_url_error

logger = logging.getLogger(__name__)

SOURCE_MESSAGE = "This target needs a valid Google Maps URL before reviews can be ingested."


def start_ingestion(engine, review_source, *, owner_id, target_id, payload):
    """Verify an ingestion request, then hand the target to the review source.

    The caller is already authenticated (require_auth). The checks below run in
    order and each one fails before the review source is called:

    1. The target exists and belongs to owner_id (one query; otherwise NotFound).
    2. The request body carries no fields. Ingestion always uses the target's
       saved source URL, so a client cannot redirect it or claim another owner.
    3. The saved source URL is present and is a usable Google Maps URL.
    """
    with Session(engine) as session:
        target = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        source_url = target.source_url

    if payload not in (None, {}):
        raise ValidationError(
            "Ingestion uses the target's saved source. Send an empty request body."
        )

    if source_url_error((source_url or "").strip()):
        raise ValidationError(SOURCE_MESSAGE, fields={"source_url": SOURCE_MESSAGE})

    logger.info("Starting ingestion for target %s", target_id)
    review_source.submit(target_id=target_id, source_url=source_url)
    return {"target_id": target_id, "status": "accepted"}
