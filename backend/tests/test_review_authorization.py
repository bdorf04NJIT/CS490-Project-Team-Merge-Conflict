"""S1-013: User B cannot read, create, or ingest review data under User A's AnalysisTarget.

Reviews and ingestion runs have no owner column. Ownership is inherited through
Review.target_id -> AnalysisTarget.owner_id, so every test seeds real review data for
User A first and proves User B can neither see it nor add to it.
"""

import io

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.review_source_csv import RawReviewBatch
from app.errors import NotFound
from app.models import IngestionRun, Review
from app.services.ingestion import import_supplied_reviews, start_ingestion

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "We couldn't find that analysis target."}}
A_REVIEWS = b"review_text,rating\nA private review one,5\nA private review two,3\n"
B_REVIEWS = b"review_text,rating\nInjected by B,1\n"


class RecordingSource:
    """Fake review provider. Records every call and returns one planted review."""

    def __init__(self):
        self.calls = []

    def submit(self, *, target_id, source_url):
        self.calls.append(target_id)
        return RawReviewBatch(
            rows=[{"snippet": "Injected by B", "rating": 1}], source_kind="serpapi_google_maps"
        )


@pytest.fixture
def source(client):
    fake = RecordingSource()
    client.application.extensions["review_source"] = fake
    return fake


def make_target(client, auth_header, user):
    response = client.post(
        "/api/targets",
        json={"name": f"{user} target", "platform": "google_maps", "source_url": SOURCE_URL},
        headers=auth_header(user),
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def upload(client, headers, target_id, csv_bytes):
    return client.post(
        f"/api/targets/{target_id}/ingestions/import",
        headers=headers,
        data={"file": (io.BytesIO(csv_bytes), "reviews.csv")},
        content_type="multipart/form-data",
    )


@pytest.fixture
def target_a(client, auth_header):
    """User A owns Target A, which already holds two imported reviews and one run."""
    target_id = make_target(client, auth_header, "user-a")
    assert upload(client, auth_header("user-a"), target_id, A_REVIEWS).status_code == 201
    return target_id


def snapshot(client):
    """Every review and run in the database, so any cross-user write shows up as a diff."""
    with Session(client.application.extensions["database"]) as session:
        reviews = sorted((r.target_id, r.text) for r in session.scalars(select(Review)))
        runs = sorted((r.target_id, r.id, r.status) for r in session.scalars(select(IngestionRun)))
        return reviews, runs


def owner_review_texts(client, auth_header, target_id):
    response = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert response.status_code == 200
    return sorted(r["text"] for r in response.get_json()["reviews"])


# --- Happy path: the owner has full access -------------------------------------------------


def test_owner_can_read_own_reviews(client, auth_header, target_a):
    assert owner_review_texts(client, auth_header, target_a) == [
        "A private review one",
        "A private review two",
    ]


# --- 1. User B cannot retrieve User A's reviews --------------------------------------------


def test_user_b_cannot_retrieve_target_a_reviews(client, auth_header, target_a):
    response = client.get(f"/api/targets/{target_a}/reviews", headers=auth_header("user-b"))
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND
    assert b"A private review" not in response.data


def test_user_b_cannot_see_target_a_ingestion_state(client, auth_header, target_a):
    response = client.get(f"/api/targets/{target_a}", headers=auth_header("user-b"))
    assert response.status_code == 404
    assert b"latest_ingestion" not in response.data


# --- 2. User B cannot submit ingestion against User A's target -----------------------------


def test_user_b_cannot_start_ingestion_on_target_a(client, auth_header, target_a, source):
    before = snapshot(client)
    response = client.post(f"/api/targets/{target_a}/ingestions", headers=auth_header("user-b"))
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND
    assert source.calls == []  # the provider was never contacted
    assert snapshot(client) == before  # no new run, no planted review


# --- 3. User B cannot create review records under User A's target --------------------------


def test_user_b_cannot_import_reviews_into_target_a(client, auth_header, target_a):
    before = snapshot(client)
    response = upload(client, auth_header("user-b"), target_a, B_REVIEWS)
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND
    assert snapshot(client) == before
    assert "Injected by B" not in owner_review_texts(client, auth_header, target_a)


def test_user_b_bad_upload_does_not_record_failed_run_on_target_a(client, auth_header, target_a):
    # An invalid file would normally record a "failed" run. For a non-owner it must not.
    before = snapshot(client)
    response = upload(client, auth_header("user-b"), target_a, b"not,a,review,csv\n")
    assert response.status_code == 404
    assert snapshot(client) == before


# --- Denials leak nothing and can't be bypassed --------------------------------------------


def test_denied_and_missing_targets_look_the_same(client, auth_header, target_a, source):
    b = auth_header("user-b")
    pairs = [
        (client.get(f"/api/targets/{t}/reviews", headers=b) for t in (target_a, "missing")),
        (client.post(f"/api/targets/{t}/ingestions", headers=b) for t in (target_a, "missing")),
        (upload(client, b, t, B_REVIEWS) for t in (target_a, "missing")),
    ]
    for other, missing in (tuple(p) for p in pairs):
        assert (other.status_code, other.get_json()) == (missing.status_code, missing.get_json())


@pytest.mark.parametrize("param", ["user_id", "userId", "owner_id", "ownerId", "owner"])
def test_forged_owner_param_does_not_unlock_reviews(client, auth_header, target_a, source, param):
    before = snapshot(client)
    b = auth_header("user-b")
    forged = {param: "user-a"}
    read = client.get(f"/api/targets/{target_a}/reviews", headers=b, query_string=forged)
    ingest = client.post(f"/api/targets/{target_a}/ingestions", headers=b, query_string=forged)
    assert read.status_code == ingest.status_code == 404
    assert source.calls == []
    assert snapshot(client) == before


def test_user_b_writes_only_to_own_target(client, auth_header, target_a):
    target_b = make_target(client, auth_header, "user-b")
    assert upload(client, auth_header("user-b"), target_b, B_REVIEWS).status_code == 201
    reviews, _ = snapshot(client)
    assert (target_b, "Injected by B") in reviews
    assert "Injected by B" not in owner_review_texts(client, auth_header, target_a)


# --- Ownership is checked BEFORE the child operation runs ----------------------------------


def test_import_checks_owner_before_reading_upload(client, target_a):
    engine = client.application.extensions["database"]
    read = []
    with pytest.raises(NotFound):
        import_supplied_reviews(
            engine, owner_id="user-b", target_id=target_a, upload=lambda: read.append(1)
        )
    assert read == []  # the uploaded file was never touched


def test_ingestion_checks_owner_before_validating_body_or_calling_source(client, target_a):
    engine = client.application.extensions["database"]
    fake = RecordingSource()
    # Even an invalid body gets NotFound (not a validation error) for a non-owner.
    with pytest.raises(NotFound):
        start_ingestion(
            engine, fake, owner_id="user-b", target_id=target_a, payload={"source_url": "x"}
        )
    assert fake.calls == []
