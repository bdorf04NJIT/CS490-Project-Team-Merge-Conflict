import pytest
from sqlalchemy import select
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


def stored(client, target_id):
    with Session(client.application.extensions["database"]) as session:
        row = session.scalars(select(AnalysisTarget).where(AnalysisTarget.id == target_id)).one()
        return (row.owner_id, row.name, row.platform, row.source_url)


def test_owner_opens_their_target_workspace(client, auth_header):
    target_id = make_target(client, auth_header, "user-a", "A cafe")
    response = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a"))
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"id", "name", "platform", "source_url", "created_at", "latest_ingestion"}
    assert body["id"] == target_id
    assert body["name"] == "A cafe"
    assert body["platform"] == "google_maps"
    assert body["source_url"] == SOURCE_URL
    assert body["latest_ingestion"] is None


def test_other_user_cannot_open_target_by_id(client, auth_header):
    target_id = make_target(client, auth_header, "user-a", "Secret cafe")
    before = stored(client, target_id)

    response = client.get(f"/api/targets/{target_id}", headers=auth_header("user-b"))

    assert response.status_code == 404
    assert response.get_json() == {
        "error": {"code": "NOT_FOUND", "message": "We couldn't find that analysis target."}
    }
    assert b"Secret cafe" not in response.data
    assert SOURCE_URL.encode() not in response.data
    assert stored(client, target_id) == before
    # The rightful owner still has access afterward (guardrails checklist item 7).
    assert client.get(f"/api/targets/{target_id}", headers=auth_header("user-a")).status_code == 200


def test_denied_and_missing_targets_look_the_same(client, auth_header):
    target_id = make_target(client, auth_header, "user-a", "A cafe")
    other = client.get(f"/api/targets/{target_id}", headers=auth_header("user-b"))
    missing = client.get("/api/targets/does-not-exist", headers=auth_header("user-b"))
    assert (other.status_code, other.get_json()) == (missing.status_code, missing.get_json())


@pytest.mark.parametrize("param", ["user_id", "userId", "owner_id", "ownerId", "owner"])
def test_client_supplied_owner_cannot_unlock_target(client, auth_header, param):
    target_id = make_target(client, auth_header, "user-a", "A cafe")
    response = client.get(
        f"/api/targets/{target_id}",
        headers=auth_header("user-b"),
        query_string={param: "user-a"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("token_kind", ["missing", "expired", "forged"])
def test_unauthenticated_workspace_is_denied_without_data(client, auth_header, token_kind):
    target_id = make_target(client, auth_header, "user-a", "Secret cafe")
    headers = {}
    if token_kind == "expired":
        headers = auth_header("user-a", expires_in=-10)
    elif token_kind == "forged":
        headers = auth_header("user-a", secret="wrong-secret-at-least-32-bytes-long!")
    response = client.get(f"/api/targets/{target_id}", headers=headers)
    assert response.status_code == 401
    assert set(response.get_json()) == {"error"}
    assert b"Secret cafe" not in response.data
