import re
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from ..errors import ValidationError
from ..models import AnalysisTarget

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
    if not source_url:
        errors["source_url"] = MESSAGES["url_missing"]
    elif len(source_url) > MAX_URL:
        errors["source_url"] = MESSAGES["url_long"]
    else:
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
            errors["source_url"] = MESSAGES["url_invalid"]
        elif not is_google_maps_url(url):
            errors["source_url"] = MESSAGES["url_not_maps"]

    if payload.get("platform") != PLATFORM:
        errors["platform"] = MESSAGES["platform"]

    if errors:
        raise ValidationError("Some target details need fixing.", fields=errors)
    return {"name": name, "platform": PLATFORM, "source_url": source_url}


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
