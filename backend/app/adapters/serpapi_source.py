"""Google Maps reviews via SerpApi, with bounded pagination and safe key failover.

The only destinations are the fixed SerpApi search/account endpoints. Credentials
stay server-side and are never included in application responses or logs.
"""

import json
import re
from datetime import UTC, datetime
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import urlopen

from ..errors import IngestionUnavailable, ValidationError
from .review_source_csv import RawReviewBatch
from .serpapi_key_pool import SerpApiKeyPool

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
ACCOUNT_ENDPOINT = "https://serpapi.com/account.json"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DATA_ID = re.compile(r"(?:!1s|[?&]ftid=)(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)")
_PLACE_ID = re.compile(r"!1s(ChIJ[A-Za-z0-9_-]+)")
ERROR_MESSAGE = "The review provider could not complete this import."
NO_CAPACITY_MESSAGE = "SerpApi currently has no available search capacity. Try again later."


def extract_serpapi_locator(source_url: str) -> dict[str, str]:
    """Extract a supported stable place identifier; never request a supplied URL."""
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


def _renewal_wait(account):
    """Conservatively hold exhausted monthly accounts until their renewal date."""
    date = account.get("plan_renewal_date")
    if isinstance(date, str):
        try:
            renewal = datetime.fromisoformat(date).replace(tzinfo=UTC)
            seconds = int((renewal - datetime.now(UTC)).total_seconds())
            if seconds > 0:
                return seconds + 3600
        except ValueError:
            pass
    # Unknown renewal: recheck account balance tomorrow, never assume capacity.
    return 24 * 3600


class SerpApiGoogleMapsSource:
    def __init__(
        self,
        api_key,
        transport=None,
        *,
        account_transport=None,
        max_pages=1,
        quota_preflight=False,
        clock=monotonic,
    ):
        # Existing single-key callers remain supported.
        keys = [api_key] if isinstance(api_key, str) else list(api_key)
        self._pool = SerpApiKeyPool(keys, clock=clock)
        self._transport = transport or self._request
        self._account_transport = account_transport or self._request
        self._preflight = quota_preflight
        self._clock = clock
        self._quota_cache = {}
        if not isinstance(max_pages, int) or not 1 <= max_pages <= 10:
            raise ValueError("SERPAPI_MAX_PAGES must be between 1 and 10")
        self._max_pages = max_pages

    @staticmethod
    def _request(url):
        with urlopen(url, timeout=20) as response:
            return response.read(MAX_RESPONSE_BYTES + 1)

    @staticmethod
    def _decode(response):
        if len(response) > MAX_RESPONSE_BYTES:
            raise ValueError("Provider response too large")
        result = json.loads(response)
        if not isinstance(result, dict):
            raise ValueError("Invalid provider response")
        return result

    def _account(self, key, *, refresh=False):
        """Check account quota without using search credits (60-second cache)."""
        cached = self._quota_cache.get(key)
        if cached and not refresh and cached[0] > self._clock():
            return cached[1]
        url = f"{ACCOUNT_ENDPOINT}?{urlencode({'api_key': key})}"
        try:
            value = self._decode(self._account_transport(url))
            if value.get("error"):
                return None
            self._quota_cache[key] = (self._clock() + 60, value)
            return value
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError):
            # The Account API can be unavailable; search errors still enforce limits.
            return None

    def _capacity(self, key, *, refresh=False):
        """Respect both monthly credits and hourly throughput limits."""
        account = self._account(key, refresh=refresh)
        if account is None:
            return True
        remaining = account.get("total_searches_left")
        if isinstance(remaining, int) and not isinstance(remaining, bool) and remaining <= 0:
            self._pool.pause(key, _renewal_wait(account))
            return False
        hourly = account.get("account_rate_limit_per_hour")
        current = account.get("this_hour_searches")
        if (
            isinstance(hourly, int)
            and isinstance(current, int)
            and not isinstance(hourly, bool)
            and not isinstance(current, bool)
            and hourly > 0
            and current >= hourly
        ):
            self._pool.pause(key, 3600)
            return False
        return True

    def _search(self, params):
        tried = set()
        while True:
            key = self._pool.acquire(tried=tried)
            if key is None:
                raise IngestionUnavailable(NO_CAPACITY_MESSAGE)
            tried.add(key)
            if self._preflight and not self._capacity(key):
                continue
            url = f"{SERPAPI_ENDPOINT}?{urlencode({**params, 'api_key': key})}"
            try:
                data = self._decode(self._transport(url))
                if data.get("error") or not isinstance(data.get("reviews"), list):
                    raise ValueError("No usable review dataset")
                return data
            except HTTPError as exc:
                if exc.code == 429:
                    # 429 can mean hourly throttling OR exhausted monthly balance.
                    # Refresh account status; never blindly retry an unavailable key.
                    if self._preflight and not self._capacity(key, refresh=True):
                        continue
                    self._pool.pause(key, 3600)
                    continue
                if exc.code in (401, 403):
                    self._pool.disable(key)
                    continue
                raise IngestionUnavailable(ERROR_MESSAGE) from None
            except (URLError, TimeoutError, OSError, ValueError, TypeError):
                raise IngestionUnavailable(ERROR_MESSAGE) from None

    def submit(self, *, target_id, source_url):
        """Collect bounded real provider pages; the caller persists the batch.

        target_id is never transmitted. No pages are silently fabricated.
        """
        del target_id
        locator = extract_serpapi_locator(source_url)
        reviews = []
        token = None
        seen_tokens = set()
        for _ in range(self._max_pages):
            params = {"engine": "google_maps_reviews", "hl": "en", **locator}
            if token:
                params["next_page_token"] = token
            data = self._search(params)
            reviews.extend(data["reviews"])
            page = data.get("serpapi_pagination")
            token = page.get("next_page_token") if isinstance(page, dict) else None
            if not isinstance(token, str) or not token or token in seen_tokens:
                break
            seen_tokens.add(token)
        return RawReviewBatch(rows=reviews, source_kind="serpapi_google_maps")
