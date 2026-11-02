import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisTarget

VALID = {
    "name": "Joe's Coffee",
    "platform": "google_maps",
    "source_url": "https://www.google.com/maps/place/Joe's+Coffee/@40.74,-74.17,17z",
}


def post(client, auth_header, payload):
    return client.post("/api/targets", json=payload, headers=auth_header())


def stored(client):
    with Session(client.application.extensions["database"]) as session:
        return session.scalars(select(AnalysisTarget)).all()


def assert_rejected(response, client, field):
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in error["fields"]
    assert stored(client) == []
    return error["fields"][field]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/maps/place/Joe's+Coffee",
        "https://google.com/maps?cid=123456789",
        "https://www.google.co.uk/maps/place/Pub",
        "https://www.google.com.au/maps/place/Cafe",
        "https://maps.google.com/?cid=123456789",
        "https://maps.app.goo.gl/AbCdEf123",
        "https://goo.gl/maps/AbCdEf123",
        "  https://www.google.com/maps/place/Spaces  ",
    ],
)
def test_valid_google_maps_target_is_accepted(client, auth_header, url):
    response = post(client, auth_header, {**VALID, "source_url": url})
    assert response.status_code == 201
    assert response.get_json()["source_url"] == url.strip()
    assert len(stored(client)) == 1


def test_name_is_trimmed_and_platform_stored(client, auth_header):
    body = post(client, auth_header, {**VALID, "name": "  Joe's Coffee  "}).get_json()
    assert body["name"] == "Joe's Coffee"
    assert body["platform"] == "google_maps"


@pytest.mark.parametrize(
    "payload",
    [
        {k: v for k, v in VALID.items() if k != "name"},
        {**VALID, "name": ""},
        {**VALID, "name": "   "},
        {**VALID, "name": None},
        {**VALID, "name": 42},
    ],
)
def test_missing_name_is_rejected(client, auth_header, payload):
    message = assert_rejected(post(client, auth_header, payload), client, "name")
    assert message == "Enter the business or place name."


def test_too_long_name_is_rejected(client, auth_header):
    response = post(client, auth_header, {**VALID, "name": "x" * 256})
    assert "255 characters" in assert_rejected(response, client, "name")


@pytest.mark.parametrize(
    "payload",
    [
        {k: v for k, v in VALID.items() if k != "source_url"},
        {**VALID, "source_url": ""},
        {**VALID, "source_url": "   "},
        {**VALID, "source_url": None},
    ],
)
def test_missing_source_url_is_rejected(client, auth_header, payload):
    message = assert_rejected(post(client, auth_header, payload), client, "source_url")
    assert message == "Enter the Google Maps URL for this place."


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "google.com/maps/place/Joe",
        "www.google.com/maps",
        "https://",
        "ftp://www.google.com/maps/place/x",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:pass@www.google.com/maps/place/x",
        "https://www.google.com:99999/maps",
        "https://www.google.com/maps/place/Joe Coffee",
    ],
)
def test_malformed_url_is_rejected(client, auth_header, url):
    message = assert_rejected(
        post(client, auth_header, {**VALID, "source_url": url}), client, "source_url"
    )
    assert message == "Enter a complete URL starting with https://."


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/place",
        "https://www.yelp.com/biz/joes-coffee",
        "https://www.amazon.com/dp/B000000",
        "https://www.google.com/search?q=joes+coffee",
        "https://www.google.com/mapsfake/place/x",
        "https://www.google.com.evil.com/maps/place/x",
        "https://evil.com/www.google.com/maps",
        "https://notgoogle.com/maps/place/x",
        "https://maps.app.goo.gl/",
        "https://goo.gl/abc123",
    ],
)
def test_non_google_maps_url_is_rejected(client, auth_header, url):
    message = assert_rejected(
        post(client, auth_header, {**VALID, "source_url": url}), client, "source_url"
    )
    assert "Google Maps link" in message


@pytest.mark.parametrize("platform", ["google", "amazon", "", None])
def test_unsupported_platform_is_rejected(client, auth_header, platform):
    assert_rejected(post(client, auth_header, {**VALID, "platform": platform}), client, "platform")


def test_all_field_problems_are_reported_together(client, auth_header):
    response = post(client, auth_header, {"name": "", "platform": "yelp", "source_url": "nope"})
    assert response.status_code == 400
    assert set(response.get_json()["error"]["fields"]) == {"name", "platform", "source_url"}
    assert stored(client) == []


def test_error_response_has_no_internal_details(client, auth_header):
    response = post(client, auth_header, {**VALID, "source_url": "https://example.com"})
    text = response.get_data(as_text=True)
    for leak in ("Traceback", "sqlalchemy", "urlsplit", "re.compile"):
        assert leak not in text


def test_valid_input_still_succeeds_after_a_rejection(client, auth_header):
    post(client, auth_header, {**VALID, "source_url": "https://example.com"})
    assert post(client, auth_header, VALID).status_code == 201
    assert len(stored(client)) == 1
