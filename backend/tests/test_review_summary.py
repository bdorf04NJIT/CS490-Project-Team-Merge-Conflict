"""S2-008: the review summary is derived from the active persisted review dataset.

Service tests write and delete Review rows directly, so the summary can only be right
if it reads persisted data. API tests prove ownership is enforced at the HTTP boundary.
"""

import io
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import AnalysisTarget, Base, IngestionRun, Review
from app.services.review_storage import persist_reviews, record_failed_run
from app.services.review_summary import active_reviews, summarize_reviews

EMPTY_DISTRIBUTION = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "We couldn't find that analysis target."}}
SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"


@pytest.fixture
def storage():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                AnalysisTarget(
                    id=target_id,
                    owner_id=owner_id,
                    name=target_id.upper(),
                    platform="google_maps",
                    source_url=f"https://www.google.com/maps/place/{target_id}",
                )
                for target_id, owner_id in (("a", "user-a"), ("b", "user-a"), ("c", "user-b"))
            ]
        )
    yield engine
    engine.dispose()


def seed(engine, target_id, ratings, *, owner_id="user-a", skipped_count=0):
    return persist_reviews(
        engine,
        owner_id=owner_id,
        target_id=target_id,
        source_kind="google_maps_csv",
        reviews=[{"text": f"{target_id} review {i}", "rating": r} for i, r in enumerate(ratings)],
        skipped_count=skipped_count,
    )


def summary(engine, target_id, owner_id="user-a"):
    return summarize_reviews(engine, owner_id=owner_id, target_id=target_id)


# --- Summary math from a known fixture -----------------------------------------------------


def test_summary_counts_and_averages_known_fixture(storage):
    seed(storage, "a", [5, 5, 4, 2, 1])
    result = summary(storage, "a")
    assert result["target_id"] == "a"
    assert result["review_count"] == 5
    assert result["average_rating"] == 3.4
    assert result["rating_distribution"] == {"1": 1, "2": 1, "3": 0, "4": 1, "5": 2}


def test_fractional_ratings_count_toward_whole_star_but_keep_exact_average(storage):
    seed(storage, "a", [4.5, 3.0])
    result = summary(storage, "a")
    assert result["rating_distribution"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 0}
    assert result["average_rating"] == 3.75


def test_target_without_reviews_has_empty_summary(storage):
    result = summary(storage, "a")
    assert result["review_count"] == 0
    assert result["average_rating"] is None
    assert result["rating_distribution"] == EMPTY_DISTRIBUTION
    assert result["latest_ingestion"] is None


# --- 1. Adding or removing persisted reviews changes the summary ---------------------------


def test_adding_persisted_review_changes_summary(storage):
    seed(storage, "a", [5, 3])
    assert summary(storage, "a")["review_count"] == 2

    seed(storage, "a", [1])  # a later run appends to the dataset
    result = summary(storage, "a")
    assert result["review_count"] == 3
    assert result["average_rating"] == 3.0
    assert result["rating_distribution"]["1"] == 1


def test_removing_persisted_review_changes_summary(storage):
    seed(storage, "a", [5, 1])
    with Session(storage) as session, session.begin():
        session.execute(delete(Review).where(Review.target_id == "a", Review.rating == 1))
    result = summary(storage, "a")
    assert result["review_count"] == 1
    assert result["average_rating"] == 5.0
    assert result["rating_distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1}


# --- Records that were not ingested never count --------------------------------------------


def test_skipped_records_are_not_counted_as_reviews(storage):
    seed(storage, "a", [4, 4], skipped_count=3)
    result = summary(storage, "a")
    assert result["review_count"] == 2
    assert result["latest_ingestion"]["status"] == "partial"
    assert result["latest_ingestion"]["skipped_count"] == 3


def test_failed_run_reports_status_without_inventing_reviews(storage):
    seed(storage, "a", [5])
    # Backdate the first run so both runs never share a timestamp (coarse Windows clock).
    with Session(storage) as session, session.begin():
        session.execute(
            update(IngestionRun).values(started_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    record_failed_run(
        storage, owner_id="user-a", target_id="a", source_kind="google_maps_csv", message="Bad"
    )
    result = summary(storage, "a")
    assert result["review_count"] == 1  # earlier persisted reviews remain the dataset
    assert result["latest_ingestion"]["status"] == "failed"


# --- 2/3. Each target's summary uses only that target's reviews ----------------------------


def test_each_target_summary_uses_only_its_own_reviews(storage):
    seed(storage, "a", [5, 5, 5])
    seed(storage, "b", [1, 2])

    a, b = summary(storage, "a"), summary(storage, "b")
    assert (a["target_id"], a["review_count"], a["average_rating"]) == ("a", 3, 5.0)
    assert (b["target_id"], b["review_count"], b["average_rating"]) == ("b", 2, 1.5)
    assert a["rating_distribution"]["1"] == 0
    assert b["rating_distribution"]["5"] == 0


def test_active_dataset_query_matches_summary_count(storage):
    """Q&A context will read active_reviews(); it must agree with the summary."""
    seed(storage, "a", [5, 4])
    seed(storage, "b", [1])
    with Session(storage) as session:
        texts = sorted(
            r.text for r in session.scalars(active_reviews(owner_id="user-a", target_id="a"))
        )
    assert texts == ["a review 0", "a review 1"]
    assert summary(storage, "a")["review_count"] == len(texts)


# --- 4. User A cannot retrieve User B's summary --------------------------------------------


def test_other_user_cannot_summarize_target(storage):
    seed(storage, "c", [5], owner_id="user-b")
    with pytest.raises(NotFound):
        summary(storage, "c", owner_id="user-a")


def test_active_dataset_excludes_another_users_target(storage):
    seed(storage, "c", [5], owner_id="user-b")
    with Session(storage) as session:
        rows = session.scalars(active_reviews(owner_id="user-a", target_id="c")).all()
    assert rows == []


def test_missing_target_raises_not_found(storage):
    with pytest.raises(NotFound):
        summary(storage, "does-not-exist")


# --- HTTP boundary -------------------------------------------------------------------------


def make_target_with_reviews(client, auth_header, user, csv_bytes):
    headers = auth_header(user)
    response = client.post(
        "/api/targets",
        json={"name": f"{user} target", "platform": "google_maps", "source_url": SOURCE_URL},
        headers=headers,
    )
    assert response.status_code == 201
    target_id = response.get_json()["id"]
    response = client.post(
        f"/api/targets/{target_id}/ingestions/import",
        headers=headers,
        data={"file": (io.BytesIO(csv_bytes), "reviews.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    return target_id


def test_owner_gets_summary_over_api(client, auth_header):
    target_id = make_target_with_reviews(
        client, auth_header, "user-a", b"review_text,rating\nGreat,5\nFine,3\nBad row,9\n"
    )
    response = client.get(f"/api/targets/{target_id}/summary", headers=auth_header("user-a"))
    assert response.status_code == 200
    body = response.get_json()
    assert body["review_count"] == 2
    assert body["average_rating"] == 4.0
    assert body["rating_distribution"] == {"1": 0, "2": 0, "3": 1, "4": 0, "5": 1}
    assert body["latest_ingestion"]["status"] == "partial"
    assert body["latest_ingestion"]["skipped_count"] == 1


def test_user_b_cannot_retrieve_user_a_summary_over_api(client, auth_header):
    target_id = make_target_with_reviews(
        client, auth_header, "user-a", b"review_text,rating\nSecret A review,5\n"
    )
    response = client.get(f"/api/targets/{target_id}/summary", headers=auth_header("user-b"))
    assert response.status_code == 404
    assert response.get_json() == NOT_FOUND
    assert b"review_count" not in response.data


def test_summary_requires_authentication(client, auth_header):
    target_id = make_target_with_reviews(
        client, auth_header, "user-a", b"review_text,rating\nGreat,5\n"
    )
    response = client.get(f"/api/targets/{target_id}/summary")
    assert response.status_code == 401
    assert b"review_count" not in response.data
