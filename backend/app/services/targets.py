from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ValidationError
from ..models import AnalysisTarget


def list_targets(engine, *, owner_id):
    """Return only the targets owned by owner_id, newest first.

    The ownership filter is applied in the database query, never in the caller.
    owner_id is intentionally omitted from the result: the caller already knows it.
    """
    with Session(engine) as session:
        rows = session.scalars(
            select(AnalysisTarget)
            .where(AnalysisTarget.owner_id == owner_id)
            .order_by(AnalysisTarget.created_at.desc(), AnalysisTarget.id)
        ).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "platform": row.platform,
                "source_url": row.source_url,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


def create_target(engine, *, owner_id, payload):
    # An allowlist rejects ownership aliases and prevents mass assignment.
    fields = {"name": 255, "platform": 100, "source_url": 2048}
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise ValidationError()
    values = {}
    for field, limit in fields.items():
        value = payload[field]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValidationError()
        values[field] = value.strip()
    try:
        url = urlsplit(values["source_url"])
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError()
    except ValueError:
        raise ValidationError() from None

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
