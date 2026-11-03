"""Short-link ingestion with mocked Google/SerpAPI; no live provider requests."""

import json

from app.adapters.serpapi_source import SerpApiGoogleMapsSource
from app.adapters.short_maps_links import ShortMapsLinkError

SHORT = "https://maps.app.goo.gl/AbCdEfGH"
LONG = "https://www.google.com/maps/place/Cafe/data=!4m2!1s0x89c259:0xa4969e07"


def make_target(client, auth_header):
    response = client.post(
        "/api/targets",
        json={"name": "A cafe", "platform": "google_maps", "source_url": SHORT},
        headers=auth_header("user-a"),
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def test_short_link_resolves_then_ingests_and_stores_reviews(client, auth_header, monkeypatch):
    target_id = make_target(client, auth_header)
    calls = []

    def resolve(url):
        calls.append(("resolve", url))
        return LONG

    def transport(url):
        calls.append(("provider", url))
        return json.dumps({"reviews": [{"snippet": "Good coffee", "rating": 5}]}).encode()

    monkeypatch.setattr("app.services.ingestion.resolve_short_maps_link", resolve)
    client.application.extensions["review_source"] = SerpApiGoogleMapsSource(
        "fake-unit-test-token", transport=transport
    )
    response = client.post(f"/api/targets/{target_id}/ingestions", headers=auth_header("user-a"))
    assert response.status_code == 202
    assert response.get_json()["imported_count"] == 1
    assert calls[0] == ("resolve", SHORT)
    assert calls[1][0] == "provider"
    assert "data_id=0x89c259" in calls[1][1]
    reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert reviews.status_code == 200
    assert [x["text"] for x in reviews.get_json()["reviews"]] == ["Good coffee"]


def test_denied_user_cannot_trigger_short_url_resolution(client, auth_header, monkeypatch):
    target_id = make_target(client, auth_header)

    def do_not_call(_):
        raise AssertionError("Denied user must not trigger redirects")

    monkeypatch.setattr("app.services.ingestion.resolve_short_maps_link", do_not_call)
    client.application.extensions["review_source"] = SerpApiGoogleMapsSource(
        "fake-unit-test-token", transport=do_not_call
    )
    response = client.post(f"/api/targets/{target_id}/ingestions", headers=auth_header("user-b"))
    assert response.status_code == 404


def test_unresolvable_link_records_failure(client, auth_header, monkeypatch):
    target_id = make_target(client, auth_header)

    def reject(_):
        raise ShortMapsLinkError("Copy the full Google Maps place URL instead.")

    monkeypatch.setattr("app.services.ingestion.resolve_short_maps_link", reject)
    client.application.extensions["review_source"] = SerpApiGoogleMapsSource(
        "fake-unit-test-token", transport=lambda _: (_ for _ in ()).throw(AssertionError())
    )
    response = client.post(f"/api/targets/{target_id}/ingestions", headers=auth_header("user-a"))
    assert response.status_code == 400
    workspace = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a"))
    assert workspace.get_json()["latest_ingestion"]["status"] == "failed"
