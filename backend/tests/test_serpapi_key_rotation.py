"""No real SerpApi credentials or live HTTP requests are used in these tests."""

import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.adapters.serpapi_key_pool import SerpApiKeyPool
from app.adapters.serpapi_source import SerpApiGoogleMapsSource
from app.errors import IngestionUnavailable

PLACE = "https://www.google.com/maps/place/Cafe/data=!4m2!1s0x89c259:0xa4969e07"


def query(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def too_many_requests(url):
    raise HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO(b"{}"))


def test_pool_deduplicates_keys_and_rotates_eligible_keys():
    now = [100.0]
    pool = SerpApiKeyPool(["a", "b", "a", "c"], clock=lambda: now[0])
    assert pool.count == 3
    assert [pool.acquire() for _ in range(4)] == ["a", "b", "c", "a"]
    pool.pause("a", 3600)
    assert [pool.acquire() for _ in range(4)] == ["b", "c", "b", "c"]
    pool.disable("b")
    pool.disable("c")
    assert pool.acquire() is None
    now[0] += 3601
    assert pool.acquire() == "a"


def test_first_key_429_fails_over_to_second_key():
    calls = []

    def fake(url):
        key = query(url)["api_key"]
        calls.append(key)
        if key == "fake-key-a":
            return too_many_requests(url)
        return json.dumps({"reviews": [{"snippet": "Real source fixture", "rating": 5}]}).encode()

    provider = SerpApiGoogleMapsSource(["fake-key-a", "fake-key-b"], transport=fake)
    result = provider.submit(target_id="private-target", source_url=PLACE)
    assert len(result.rows) == 1
    assert calls == ["fake-key-a", "fake-key-b"]
    provider.submit(target_id="private-target", source_url=PLACE)
    assert calls[-1] == "fake-key-b"


def test_monthly_exhaustion_skips_first_key_before_search():
    searched = []

    def account(url):
        key = query(url)["api_key"]
        remaining = 0 if key == "fake-key-a" else 24
        return json.dumps(
            {"total_searches_left": remaining, "plan_renewal_date": "2099-01-01"}
        ).encode()

    def search(url):
        searched.append(query(url)["api_key"])
        return b'{"reviews": [{"snippet": "An actual review", "rating": 4}]}'

    provider = SerpApiGoogleMapsSource(
        ["fake-key-a", "fake-key-b"],
        transport=search,
        account_transport=account,
        quota_preflight=True,
    )
    provider.submit(target_id="t", source_url=PLACE)
    assert searched == ["fake-key-b"]


def test_hourly_limit_causes_temporary_cooldown_without_live_search():
    usage = {"fake-key-a": 10, "fake-key-b": 1}

    def account(url):
        return json.dumps(
            {
                "total_searches_left": 100,
                "account_rate_limit_per_hour": 10,
                "this_hour_searches": usage[query(url)["api_key"]],
            }
        ).encode()

    used = []

    def search(url):
        used.append(query(url)["api_key"])
        return b'{"reviews": [{"snippet": "Visit", "rating": 5}]}'

    source = SerpApiGoogleMapsSource(
        ["fake-key-a", "fake-key-b"],
        transport=search,
        account_transport=account,
        quota_preflight=True,
    )
    source.submit(target_id="t", source_url=PLACE)
    assert used == ["fake-key-b"]


def test_no_available_key_never_makes_provider_request_or_leaks_secrets():
    seen = []

    def fake(url):
        seen.append(url)
        return too_many_requests(url)

    secret = "sensitive-unit-test-secret"
    source = SerpApiGoogleMapsSource([secret], transport=fake)
    with pytest.raises(IngestionUnavailable) as exc:
        source.submit(target_id="t", source_url=PLACE)
    assert len(seen) == 1
    assert secret not in str(exc.value)
    assert "capacity" in str(exc.value).lower()


def test_bounded_pagination_uses_provider_token_and_preserves_real_rows():
    calls = []

    def fake(url):
        values = query(url)
        calls.append(values)
        page = len(calls)
        return json.dumps(
            {
                "reviews": [
                    {"review_id": f"review-{page}", "snippet": f"Text {page}", "rating": 4}
                ],
                "serpapi_pagination": {"next_page_token": f"page-{page}"},
            }
        ).encode()

    source = SerpApiGoogleMapsSource("fake-key-a", transport=fake, max_pages=3)
    result = source.submit(target_id="private-target", source_url=PLACE)
    assert [r["review_id"] for r in result.rows] == ["review-1", "review-2", "review-3"]
    assert [q.get("next_page_token") for q in calls] == [None, "page-1", "page-2"]
    assert all("target_id" not in q for q in calls)


def sorted_pages(url):
    """One short page per sort order, overlapping like the real provider."""
    pages = {
        None: ["r1", "r2", "r3"],
        "newestFirst": ["r3", "r4", "r5"],
        "ratingLow": ["r6", "r1"],
    }
    ids = pages.get(query(url).get("sort_by"), [])
    return json.dumps(
        {"reviews": [{"review_id": i, "snippet": f"Text {i}", "rating": 3} for i in ids]}
    ).encode()


def test_extra_sort_orders_add_only_new_real_reviews():
    calls = []

    def fake(url):
        calls.append(query(url).get("sort_by"))
        return sorted_pages(url)

    source = SerpApiGoogleMapsSource(
        "fake-key-a", transport=fake, extra_sorts=("newestFirst", "ratingLow")
    )
    result = source.submit(target_id="t", source_url=PLACE)
    assert [r["review_id"] for r in result.rows] == ["r1", "r2", "r3", "r4", "r5", "r6"]
    assert calls == [None, "newestFirst", "ratingLow"]


def test_extra_sort_failure_keeps_reviews_already_collected():
    def fake(url):
        if query(url).get("sort_by"):
            raise HTTPError(url, 500, "Server Error", {}, io.BytesIO(b"{}"))
        return sorted_pages(url)

    source = SerpApiGoogleMapsSource("fake-key-a", transport=fake, extra_sorts=("newestFirst",))
    result = source.submit(target_id="t", source_url=PLACE)
    assert [r["review_id"] for r in result.rows] == ["r1", "r2", "r3"]


def test_topics_top_up_until_minimum_most_mentioned_first():
    calls = []

    def fake(url):
        values = query(url)
        calls.append(values.get("topic_id"))
        by_topic = {None: ["r1", "r2"], "busy": ["r2", "r3"], "quiet": ["r4"], "never": ["r5"]}
        ids = by_topic[values.get("topic_id")]
        body = {"reviews": [{"review_id": i, "snippet": i, "rating": 4} for i in ids]}
        if values.get("topic_id") is None:
            body["topics"] = [
                {"id": "quiet", "mentions": 3},
                {"id": "busy", "mentions": 50},
                {"id": "never", "mentions": 1},
                {"keyword": "no id"},
            ]
        return json.dumps(body).encode()

    source = SerpApiGoogleMapsSource("fake-key-a", transport=fake, min_reviews=4, max_topics=3)
    result = source.submit(target_id="t", source_url=PLACE)
    assert [r["review_id"] for r in result.rows] == ["r1", "r2", "r3", "r4"]
    # Stops once the minimum is reached, so the least mentioned topic is never fetched.
    assert calls == [None, "busy", "quiet"]


def test_invalid_key_401_is_quarantined_without_reporting_key():
    from urllib.error import HTTPError

    seen = []

    def fake(url):
        key = query(url)["api_key"]
        seen.append(key)
        if key == "invalid-fake-key":
            raise HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        return b'{"reviews": [{"snippet": "Text", "rating": 5}]}'

    provider = SerpApiGoogleMapsSource(["invalid-fake-key", "good-fake-key"], transport=fake)
    provider.submit(target_id="t", source_url=PLACE)
    provider.submit(target_id="t", source_url=PLACE)
    assert seen.count("invalid-fake-key") == 1


def test_nonquota_error_does_not_burn_through_other_keys():
    seen = []

    def fake(url):
        seen.append(query(url)["api_key"])
        raise HTTPError(url, 400, "Bad Request", {}, io.BytesIO(b"{}"))

    source = SerpApiGoogleMapsSource(["a", "b"], transport=fake)
    with pytest.raises(IngestionUnavailable):
        source.submit(target_id="t", source_url=PLACE)
    assert len(seen) == 1
