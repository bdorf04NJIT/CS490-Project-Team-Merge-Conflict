import pytest
from app.models import AnalysisTarget
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

PAYLOAD = {"name": "Coffee shop", "platform": "google", "source_url": "https://example.com/place"}


def stored_targets(client):
    with Session(client.application.extensions["database"]) as session:
        return session.scalars(select(AnalysisTarget)).all()


def test_creation_persists_verified_owners(client, auth_header):
    ids = []
    for user in ("user-a", "user-b"):
        response = client.post("/api/targets", json=PAYLOAD, headers=auth_header(user))
        assert response.status_code == 201
        body = response.get_json()
        assert body["owner_id"] == user
        assert body["name"] == PAYLOAD["name"]
        ids.append(body["id"])
    assert ids[0] != ids[1]
    # Reopen the database through a new engine: ownership survives beyond the request.
    engine = create_engine(client.application.config["DATABASE_URL"])
    try:
        with Session(engine) as session:
            rows = session.scalars(select(AnalysisTarget)).all()
            assert {row.id: row.owner_id for row in rows} == dict(zip(ids, ("user-a", "user-b")))
            assert all(row.created_at is not None for row in rows)
    finally:
        engine.dispose()


@pytest.mark.parametrize("field", ["userId", "ownerId", "user_id", "owner_id", "owner", "id"])
def test_client_cannot_assign_ownership(client, auth_header, field):
    response = client.post(
        "/api/targets", json={**PAYLOAD, field: "user-b"}, headers=auth_header("user-a")
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert stored_targets(client) == []
    # The rightful user can still create after rejection.
    assert client.post("/api/targets", json=PAYLOAD, headers=auth_header("user-a")).status_code == 201
    assert [row.owner_id for row in stored_targets(client)] == ["user-a"]


@pytest.mark.parametrize("token_kind", ["missing", "expired", "forged"])
def test_unauthenticated_creation_writes_nothing(client, auth_header, token_kind):
    headers = {}
    if token_kind == "expired":
        headers = auth_header(expires_in=-10)
    elif token_kind == "forged":
        headers = auth_header(secret="wrong-secret-at-least-32-bytes-long!")
    response = client.post("/api/targets", json=PAYLOAD, headers=headers)
    assert response.status_code == 401
    assert set(response.get_json()) == {"error"}
    assert stored_targets(client) == []


@pytest.mark.parametrize("payload", [None, [], {}, {**PAYLOAD, "name": " "}, {**PAYLOAD, "source_url": "file:///etc/passwd"}])
def test_invalid_creation_writes_nothing(client, auth_header, payload):
    response = client.post("/api/targets", json=payload, headers=auth_header())
    assert response.status_code == 400
    assert stored_targets(client) == []
