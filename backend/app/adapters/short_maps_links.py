"""Resolve Google Maps share links without fetching arbitrary user-supplied hosts.

Only known HTTPS Google redirect hosts are contacted. Response bodies are never
read. This is deliberately narrow: JS-only redirects are not followed.
"""

import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_REDIRECTS = 5
_GOOGLE_HOST = re.compile(r"^(?:www\.)?google\.(?:com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})$")
_MAPS_GOOGLE_HOST = re.compile(r"^maps\.google\.(?:com|[a-z]{2}|co\.[a-z]{2}|com\.[a-z]{2})$")


class ShortMapsLinkError(ValueError):
    """Share link cannot be resolved securely; request a full Maps place URL."""


def _parts(url):
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port is not None
        ):
            return None
        return parts
    except ValueError:
        return None


def is_short_maps_link(url):
    parts = _parts(url)
    if not parts:
        return False
    host = parts.hostname.lower()
    return (host == "maps.app.goo.gl" and bool(parts.path.strip("/"))) or (
        host == "goo.gl" and parts.path.startswith("/maps/") and parts.path != "/maps/"
    )


def _allowed_google_hop(url):
    parts = _parts(url)
    if parts is None:
        return False
    host = parts.hostname.lower()
    return host in {"maps.app.goo.gl", "goo.gl"} or bool(
        _GOOGLE_HOST.fullmatch(host) or _MAPS_GOOGLE_HOST.fullmatch(host)
    )


def _is_full_maps_url(url):
    parts = _parts(url)
    if parts is None:
        return False
    host = parts.hostname.lower()
    path = parts.path.lower()
    return bool(
        (_GOOGLE_HOST.fullmatch(host) and (path == "/maps" or path.startswith("/maps/")))
        or _MAPS_GOOGLE_HOST.fullmatch(host)
    )


class _GoogleRedirectsOnly(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self._hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._hops += 1
        if self._hops > MAX_REDIRECTS or not _allowed_google_hop(newurl):
            raise ShortMapsLinkError(
                "The Google Maps share link redirects to an unsupported address."
            )
        return Request(
            newurl,
            headers={"User-Agent": "ReviewLensAI/1.0"},
            method=req.get_method(),
            origin_req_host=req.origin_req_host,
            unverifiable=True,
        )


def resolve_short_maps_link(url, *, opener_factory=None):
    """Return full Google Maps URL; do not read any response bodies.

    In the rare case HEAD is unsupported or leaves the short URL unresolved,
    try GET. Redirects remain restricted to known Google HTTPS hosts.
    """
    if not is_short_maps_link(url):
        return url
    factory = opener_factory or (lambda: build_opener(_GoogleRedirectsOnly()))
    for method in ("HEAD", "GET"):
        try:
            opener = factory()
            with opener.open(Request(url, method=method), timeout=8) as response:
                final_url = response.geturl()
            if _is_full_maps_url(final_url):
                return final_url
        except ShortMapsLinkError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass
    raise ShortMapsLinkError(
        "Unable to expand this Google Maps share link. Open it in a browser and "
        "copy the full Google Maps place URL instead."
    )
