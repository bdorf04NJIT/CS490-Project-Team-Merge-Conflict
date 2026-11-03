"""S1-012: User B cannot read or modify User A's AnalysisTarget, even with its id."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisTarget

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "We couldn't find that analysis target."}}


def make_target(client, auth_header, user="user-a", name="Target A"):
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
        return (row.owner_id, row.name, row.platform, row.source_url, row.created_at)


def test_owner_can_update_own_target(client, auth_header):
    target_id = make_target(client, auth_header)
    response = client.patch(
        f"/api/targets/{target_id}", json={"name": "Renamed"}, headers=auth_header("user-a")
    )
    assert response.status_code == 200
    assert response.get_json()["name"] == "Renamed"
    assert stored(client, target_id)[:2] == ("user-a", "Renamed")


def test_user_b_cannot_retrieve_target_a(client, auth_header):
    target_id = make_target(client, auth_header)
    response = client.get(f"/api/targets/{target_id}", headers=auth_header("user-b"))
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND
    assert b"Target A" not in response.data


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Hijacked"},
        {"source_url": "https://www.google.com/maps/place/Elsewhere"},
        {"owner_id": "user-b"},  # invalid body must still look like "not found"
        {},
    ],
)
def test_user_b_cannot_modify_target_a(client, auth_header, body):
    target_id = make_target(client, auth_header)
    before = stored(client, target_id)

    response = client.patch(f"/api/targets/{target_id}", json=body, headers=auth_header("user-b"))

    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND
    assert stored(client, target_id) == before
    # Target A is still intact and readable by its owner.
    owner_view = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a"))
    assert owner_view.get_json()["name"] == "Target A"


def test_denied_and_missing_targets_look_the_same(client, auth_header):
    target_id = make_target(client, auth_header)
    for method in (client.get, client.patch):
        kwargs = {"json": {"name": "X"}} if method is client.patch else {}
        other = method(f"/api/targets/{target_id}", headers=auth_header("user-b"), **kwargs)
        missing = method("/api/targets/does-not-exist", headers=auth_header("user-b"), **kwargs)
        assert (other.status_code, other.get_json()) == (missing.status_code, missing.get_json())


@pytest.mark.parametrize("param", ["user_id", "userId", "owner_id", "ownerId", "owner"])
def test_forged_owner_query_param_does_not_grant_access(client, auth_header, param):
    target_id = make_target(client, auth_header)
    before = stored(client, target_id)
    get = client.get(
        f"/api/targets/{target_id}", headers=auth_header("user-b"), query_string={param: "user-a"}
    )
    patch = client.patch(
        f"/api/targets/{target_id}",
        json={"name": "Hijacked"},
        headers=auth_header("user-b"),
        query_string={param: "user-a"},
    )
    assert get.status_code == patch.status_code == 404
    assert stored(client, target_id) == before


def test_user_b_can_still_modify_own_target(client, auth_header):
    a_id = make_target(client, auth_header, "user-a", "Target A")
    b_id = make_target(client, auth_header, "user-b", "Target B")
    response = client.patch(
        f"/api/targets/{b_id}", json={"name": "B renamed"}, headers=auth_header("user-b")
    )
    assert response.status_code == 200
    assert stored(client, a_id)[1] == "Target A"
    assert stored(client, b_id)[1] == "B renamed"


@pytest.mark.parametrize("body", [{"owner_id": "user-b"}, {"platform": "yelp"}, {}, ["x"]])
def test_owner_cannot_edit_protected_fields(client, auth_header, body):
    target_id = make_target(client, auth_header)
    before = stored(client, target_id)
    response = client.patch(f"/api/targets/{target_id}", json=body, headers=auth_header("user-a"))
    assert response.status_code == 400
    assert stored(client, target_id) == before


def test_unauthenticated_patch_is_rejected(client, auth_header):
    target_id = make_target(client, auth_header)
    before = stored(client, target_id)
    response = client.patch(f"/api/targets/{target_id}", json={"name": "Anon"})
    assert response.status_code == 401
    assert stored(client, target_id) == before
