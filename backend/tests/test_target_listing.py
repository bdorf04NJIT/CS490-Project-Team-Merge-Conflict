from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models import AnalysisTarget

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"


def make_target(client, auth_header, user, name):
    response = client.post(
        "/api/targets",
        json={"name": name, "platform": "google_maps", "source_url": SOURCE_URL},
        headers=auth_header(user),
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def list_ids(client, auth_header, user, **kwargs):
    response = client.get("/api/targets", headers=auth_header(user), **kwargs)
    assert response.status_code == 200
    return [t["id"] for t in response.get_json()["targets"]]


def test_user_a_sees_only_user_a_targets(client, auth_header):
    a1 = make_target(client, auth_header, "user-a", "A one")
    a2 = make_target(client, auth_header, "user-a", "A two")
    make_target(client, auth_header, "user-b", "B one")
    assert sorted(list_ids(client, auth_header, "user-a")) == sorted([a1, a2])


def test_user_b_sees_only_user_b_targets(client, auth_header):
    make_target(client, auth_header, "user-a", "A one")
    b1 = make_target(client, auth_header, "user-b", "B one")
    assert list_ids(client, auth_header, "user-b") == [b1]


def test_user_b_never_receives_user_a_data(client, auth_header):
    a1 = make_target(client, auth_header, "user-a", "Secret cafe")
    make_target(client, auth_header, "user-b", "B one")
    response = client.get("/api/targets", headers=auth_header("user-b"))
    assert a1 not in [t["id"] for t in response.get_json()["targets"]]
    assert b"Secret cafe" not in response.data
    # The rightful owner is unaffected afterward (guardrails checklist item 7).
    assert list_ids(client, auth_header, "user-a") == [a1]


@pytest.mark.parametrize("param", ["user_id", "userId", "owner_id", "ownerId", "owner"])
def test_client_supplied_owner_is_ignored(client, auth_header, param):
    make_target(client, auth_header, "user-a", "A one")
    b1 = make_target(client, auth_header, "user-b", "B one")
    # User B asks for user-a's data via a query param; the token still decides.
    assert list_ids(client, auth_header, "user-b", query_string={param: "user-a"}) == [b1]


def test_empty_list_for_user_without_targets(client, auth_header):
    make_target(client, auth_header, "user-a", "A one")
    response = client.get("/api/targets", headers=auth_header("user-b"))
    assert response.status_code == 200
    assert response.get_json() == {"targets": []}


def test_list_returns_display_fields_and_omits_owner(client, auth_header):
    make_target(client, auth_header, "user-a", "A one")
    target = client.get("/api/targets", headers=auth_header("user-a")).get_json()["targets"][0]
    assert set(target) == {"id", "name", "platform", "source_url", "created_at"}
    assert target["name"] == "A one"
    assert target["platform"] == "google_maps"
    assert target["source_url"] == SOURCE_URL


def test_targets_are_listed_newest_first(client, auth_header):
    with Session(client.application.extensions["database"]) as session, session.begin():
        for name, day in (("old", 1), ("new", 3), ("mid", 2)):
            session.add(
                AnalysisTarget(
                    owner_id="user-a",
                    name=name,
                    platform="google_maps",
                    source_url=SOURCE_URL,
                    created_at=datetime(2026, 1, day, tzinfo=UTC),
                )
            )
    response = client.get("/api/targets", headers=auth_header("user-a"))
    assert [t["name"] for t in response.get_json()["targets"]] == ["new", "mid", "old"]


@pytest.mark.parametrize("token_kind", ["missing", "expired", "forged"])
def test_unauthenticated_list_is_denied_without_data(client, auth_header, token_kind):
    make_target(client, auth_header, "user-a", "Secret cafe")
    headers = {}
    if token_kind == "expired":
        headers = auth_header("user-a", expires_in=-10)
    elif token_kind == "forged":
        headers = auth_header("user-a", secret="wrong-secret-at-least-32-bytes-long!")
    response = client.get("/api/targets", headers=headers)
    assert response.status_code == 401
    assert set(response.get_json()) == {"error"}
    assert b"Secret cafe" not in response.data
