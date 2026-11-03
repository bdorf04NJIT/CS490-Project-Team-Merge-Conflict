import json

import pytest

from app.adapters.review_source_csv import SourceFormatError, parse_review_csv
from app.adapters.serpapi_source import SerpApiGoogleMapsSource, extract_serpapi_locator
from app.errors import IngestionUnavailable, ValidationError


def test_csv_reads_supplied_reviews_without_inventing_data():
    batch = parse_review_csv(b"review_text,rating,reviewer\nGreat coffee,5,Alice\nNot hot,2,Bob\n")
    assert batch.source_kind == "google_maps_csv"
    assert [row["review_text"] for row in batch.rows] == ["Great coffee", "Not hot"]


@pytest.mark.parametrize("csv_bytes", [b"", b"not a review export", b"rating\n4\n", b"\xff"])
def test_invalid_csv_rejected(csv_bytes):
    with pytest.raises(SourceFormatError):
        parse_review_csv(csv_bytes)


def test_csv_preserves_invalid_rows_for_normalizer_to_count():
    batch = parse_review_csv(b"review_text,rating\nGood,5\n,invalid\n")
    assert len(batch.rows) == 2


def test_google_maps_data_id_is_parsed_from_full_place_link():
    locator = extract_serpapi_locator(
        "https://www.google.com/maps/place/Cafe/data=!4m2!1s0x89c259:0xa4969e07"
    )
    assert locator == {"data_id": "0x89c259:0xa4969e07"}


def test_place_id_is_parsed_from_query():
    assert extract_serpapi_locator(
        "https://www.google.com/maps/search/?api=1&query=Cafe&query_place_id=ChIJ1234567890"
    ) == {"place_id": "ChIJ1234567890"}


def test_short_maps_link_reports_clear_limitation():
    with pytest.raises(ValidationError, match="Shortened links"):
        extract_serpapi_locator("https://maps.app.goo.gl/shortlink")


def test_provider_uses_fixed_host_and_returns_actual_raw_reviews():
    urls = []

    def fake_transport(url):
        urls.append(url)
        return json.dumps({"reviews": [{"rating": 5, "snippet": "Great service"}]}).encode()

    source = SerpApiGoogleMapsSource("private-test-token", transport=fake_transport)
    batch = source.submit(
        target_id="local-target",
        source_url=("https://www.google.com/maps/place/Cafe/data=!4m2!1s0x89c259:0xa4969e07"),
    )
    assert batch.rows == [{"rating": 5, "snippet": "Great service"}]
    assert urls[0].startswith("https://serpapi.com/search.json?")
    assert "target_id" not in urls[0]


def test_provider_failure_never_exposes_api_key():
    source = SerpApiGoogleMapsSource("sensitive-example-key", transport=lambda _: b"{}")
    with pytest.raises(IngestionUnavailable) as error:
        source.submit(
            target_id="t",
            source_url=("https://www.google.com/maps/place/Cafe/data=!4m2!1s0x89c259:0xa4969e07"),
        )
    assert "sensitive-example-key" not in str(error.value)
