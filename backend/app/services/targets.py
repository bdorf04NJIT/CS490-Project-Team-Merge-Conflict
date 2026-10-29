from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from ..errors import ValidationError
from ..models import AnalysisTarget


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
            "id": target.id, "owner_id": target.owner_id,
            "name": target.name, "platform": target.platform,
            "source_url": target.source_url,
            "created_at": target.created_at.isoformat(),
        }
    return result
