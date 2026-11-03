"""Google Maps review extraction through SerpApi's structured JSON endpoint.

No requests are made to user-provided URLs (SSRF guard). Only SerpApi is contacted.
Requires SERPAPI_API_KEY server-side. Network calls are isolated/mocked in tests.
"""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import urlopen

from ..errors import IngestionUnavailable, ValidationError
from .review_source_csv import RawReviewBatch

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
# Google Maps embeds its stable data_id in the /data= segment of full place links.
_DATA_ID = re.compile(r"(?:!1s|[?&]ftid=)(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)")
_PLACE_ID = re.compile(r"!1s(ChIJ[A-Za-z0-9_-]+)")


def extract_serpapi_locator(source_url: str) -> dict[str, str]:
    """Extract a supported stable place identifier; never scrape arbitrary links."""
    decoded = unquote(source_url)
    qs = parse_qs(urlsplit(decoded).query)
    place_ids = qs.get("query_place_id", []) or qs.get("place_id", [])
    if place_ids and re.fullmatch(r"[A-Za-z0-9_-]{8,255}", place_ids[0]):
        return {"place_id": place_ids[0]}
    match = _DATA_ID.search(decoded)
    if match:
        return {"data_id": match.group(1)}
    match = _PLACE_ID.search(decoded)
    if match:
        return {"place_id": match.group(1)}
    raise ValidationError(
        "Use a full Google Maps place link containing a Google place identifier. "
        "Shortened links cannot be extracted automatically yet."
    )


class SerpApiGoogleMapsSource:
    def __init__(self, api_key, transport=None):
        self._api_key = api_key
        self._transport = transport or self._request

    @staticmethod
    def _request(url):
        with urlopen(url, timeout=20) as response:
            return response.read(2 * 1024 * 1024 + 1)

    def submit(self, *, target_id, source_url):
        """Return real raw reviews; persistence is handled by the caller.

        The target identifier is deliberately not sent to the external provider.
        """
        locator = extract_serpapi_locator(source_url)
        params = {"engine": "google_maps_reviews", "hl": "en", **locator, "api_key": self._api_key}
        url = f"{SERPAPI_ENDPOINT}?{urlencode(params)}"
        try:
            response = self._transport(url)
            if len(response) > 2 * 1024 * 1024:
                raise ValueError("Provider response too large")
            data = json.loads(response)
            if not isinstance(data, dict) or data.get("error"):
                raise ValueError("Provider did not return a usable response")
            reviews = data.get("reviews")
            if not isinstance(reviews, list):
                raise ValueError("Provider returned no review dataset")
            return RawReviewBatch(rows=reviews, source_kind="serpapi_google_maps")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError):
            # Do not expose the request URL, which contains the private provider key.
            raise IngestionUnavailable(
                "The review provider could not complete this import."
            ) from None
