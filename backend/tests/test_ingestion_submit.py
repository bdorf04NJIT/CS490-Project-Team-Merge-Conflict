import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.adapters.review_source import UnconfiguredReviewSource
from app.models import AnalysisTarget

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"


class FakeReviewSource:
    def __init__(self):
        self.calls = []

    def submit(self, *, target_id, source_url):
        self.calls.append((target_id, source_url))


@pytest.fixture
def source(client):
    fake = FakeReviewSource()
    client.application.extensions["review_source"] = fake
    return fake


def make_target(client, auth_header, user="user-a", name="A cafe"):
    response = client.post(
        "/api/targets",
        json={"name": name, "platform": "google_maps", "source_url": SOURCE_URL},
        headers=auth_header(user),
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def ingest(client, target_id, headers, **kwargs):
    return client.post(f"/api/targets/{target_id}/ingestions", headers=headers, **kwargs)


def set_source_url(client, target_id, value):
    with Session(client.application.extensions["database"]) as session, session.begin():
        session.execute(
            update(AnalysisTarget).where(AnalysisTarget.id == target_id).values(source_url=value)
        )


def stored(client, target_id):
    with Session(client.application.extensions["database"]) as session:
        row = session.scalars(select(AnalysisTarget).where(AnalysisTarget.id == target_id)).one()
        return (row.owner_id, row.name, row.platform, row.source_url)


def test_owner_starts_ingestion_with_saved_source(client, auth_header, source):
    target_id = make_target(client, auth_header)
    response = ingest(client, target_id, auth_header("user-a"))
    assert response.status_code == 202
    assert response.get_json() == {"target_id": target_id, "status": "accepted"}
    assert source.calls == [(target_id, SOURCE_URL)]


def test_empty_json_body_is_accepted(client, auth_header, source):
    target_id = make_target(client, auth_header)
    response = ingest(client, target_id, auth_header("user-a"), json={})
    assert response.status_code == 202
    assert len(source.calls) == 1


def test_other_user_cannot_start_ingestion(client, auth_header, source):
    target_id = make_target(client, auth_header, name="Secret cafe")
    before = stored(client, target_id)

    response = ingest(client, target_id, auth_header("user-b"))

    assert response.status_code == 404
    assert response.get_json() == {
        "error": {"code": "NOT_FOUND", "message": "We couldn't find that analysis target."}
    }
    assert b"Secret cafe" not in response.data
    assert SOURCE_URL.encode() not in response.data
    assert source.calls == []
    assert stored(client, target_id) == before
    # The rightful owner can still start ingestion afterward.
    assert ingest(client, target_id, auth_header("user-a")).status_code == 202
    assert source.calls == [(target_id, SOURCE_URL)]


def test_denied_and_missing_targets_look_the_same(client, auth_header, source):
    target_id = make_target(client, auth_header)
    other = ingest(client, target_id, auth_header("user-b"))
    missing = ingest(client, "does-not-exist", auth_header("user-b"))
    assert (other.status_code, other.get_json()) == (missing.status_code, missing.get_json())
    assert source.calls == []


@pytest.mark.parametrize("param", ["user_id", "userId", "owner_id", "ownerId", "owner"])
def test_forged_owner_cannot_unlock_another_users_target(client, auth_header, source, param):
    target_id = make_target(client, auth_header)
    response = ingest(
        client,
        target_id,
        auth_header("user-b"),
        json={param: "user-a"},
        query_string={param: "user-a"},
    )
    assert response.status_code == 404
    assert source.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"owner_id": "user-b"},
        {"source_url": "https://www.google.com/maps/place/Elsewhere"},
        ["unexpected"],
        "text",
    ],
)
def test_owner_cannot_send_fields_with_the_request(client, auth_header, source, body):
    target_id = make_target(client, auth_header)
    response = ingest(client, target_id, auth_header("user-a"), json=body)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert source.calls == []


@pytest.mark.parametrize(
    "bad_url", ["", "   ", "not a url", "https://example.com/place", "javascript:alert(1)"]
)
def test_missing_or_unusable_source_fails_before_ingestion(client, auth_header, source, bad_url):
    target_id = make_target(client, auth_header)
    set_source_url(client, target_id, bad_url)

    response = ingest(client, target_id, auth_header("user-a"))

    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert set(error["fields"]) == {"source_url"}
    assert source.calls == []


@pytest.mark.parametrize("token_kind", ["missing", "expired", "forged"])
def test_unauthenticated_request_is_denied_before_ingestion(
    client, auth_header, source, token_kind
):
    target_id = make_target(client, auth_header, name="Secret cafe")
    headers = {}
    if token_kind == "expired":
        headers = auth_header("user-a", expires_in=-10)
    elif token_kind == "forged":
        headers = auth_header("user-a", secret="wrong-secret-at-least-32-bytes-long!")
    response = ingest(client, target_id, headers)
    assert response.status_code == 401
    assert set(response.get_json()) == {"error"}
    assert b"Secret cafe" not in response.data
    assert source.calls == []


def test_unconfigured_source_reports_unavailable(client, auth_header):
    assert isinstance(client.application.extensions["review_source"], UnconfiguredReviewSource)
    target_id = make_target(client, auth_header)
    response = ingest(client, target_id, auth_header("user-a"))
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "INGESTION_UNAVAILABLE"
