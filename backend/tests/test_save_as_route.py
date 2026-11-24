"""S3-003: HTTP surface for Save As — POST /api/targets/<id>/copies."""

from sqlalchemy.orm import Session

from app.models import AnalysisTarget
from app.services.review_storage import persist_reviews

SOURCE = {
    "owner_id": "user-a",
    "name": "Joe's Coffee",
    "platform": "google_maps",
    "source_url": "https://www.google.com/maps/place/Joe's+Coffee",
}
REVIEWS = [
    {"text": "Great coffee", "rating": 5.0, "source_review_id": "r1"},
    {"text": "Too slow", "rating": 2.0, "source_review_id": "r2"},
]


def make_source(client):
    engine = client.application.extensions["database"]
    with Session(engine) as session, session.begin():
        target = AnalysisTarget(**SOURCE)
        session.add(target)
        session.flush()
        target_id = target.id
    persist_reviews(
        engine,
        owner_id="user-a",
        target_id=target_id,
        reviews=REVIEWS,
        skipped_count=0,
        source_kind="google_maps",
    )
    return target_id


def test_owner_saves_as_a_new_named_analysis(client, auth_header):
    source_id = make_source(client)
    response = client.post(
        f"/api/targets/{source_id}/copies",
        json={"name": "Joe's backup"},
        headers=auth_header("user-a"),
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["id"] != source_id
    assert body["name"] == "Joe's backup"
    assert body["source_url"] == SOURCE["source_url"]


def test_copy_is_listed_and_openable_with_its_reviews(client, auth_header):
    source_id = make_source(client)
    copy_id = client.post(
        f"/api/targets/{source_id}/copies",
        json={"name": "Backup"},
        headers=auth_header("user-a"),
    ).get_json()["id"]

    reviews = client.get(
        f"/api/targets/{copy_id}/reviews", headers=auth_header("user-a")
    ).get_json()["reviews"]
    assert sorted(r["text"] for r in reviews) == ["Great coffee", "Too slow"]


def test_empty_name_is_rejected(client, auth_header):
    source_id = make_source(client)
    response = client.post(
        f"/api/targets/{source_id}/copies",
        json={"name": "   "},
        headers=auth_header("user-a"),
    )
    assert response.status_code == 400
    assert "name" in response.get_json()["error"]["fields"]


def test_non_owner_gets_not_found_and_creates_nothing(client, auth_header):
    source_id = make_source(client)
    response = client.post(
        f"/api/targets/{source_id}/copies",
        json={"name": "Stolen"},
        headers=auth_header("user-b"),
    )
    assert response.status_code == 404
    # user-b has no analyses of their own as a result of the denied copy.
    listed = client.get("/api/targets", headers=auth_header("user-b")).get_json()["targets"]
    assert listed == []


def test_unauthenticated_save_as_is_rejected(client):
    source_id = make_source(client)
    response = client.post(f"/api/targets/{source_id}/copies", json={"name": "X"})
    assert response.status_code == 401
