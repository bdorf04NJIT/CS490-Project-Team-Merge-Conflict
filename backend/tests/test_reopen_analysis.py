"""S3-004: a returning authenticated user can reopen a saved analysis.

Reopening restores the ReviewLens workspace for the analysis. At minimum it restores:
the analysis name, source/entity context, current ingestion state, current persisted
review dataset, and the ingestion summary. Q&A history is addressed separately (S3-007).

These tests reopen through the same HTTP endpoints the frontend uses, with a fresh
session token to represent a user returning in a later session.
"""

import time

from app.services.review_storage import persist_reviews

SOURCE_URL = "https://www.google.com/maps/place/Joe's+Coffee"
REVIEWS = [
    {"text": "Great coffee", "rating": 5.0, "source_review_id": "r1"},
    {"text": "Too slow", "rating": 2.0, "source_review_id": "r2"},
    {"text": "Friendly staff", "rating": 4.0, "source_review_id": "r3"},
]


def create_and_ingest(client, auth_header, owner="user-a"):
    """Create an analysis and give it a persisted review dataset, as an earlier session would."""
    target_id = client.post(
        "/api/targets",
        json={"name": "Joe's Coffee", "platform": "google_maps", "source_url": SOURCE_URL},
        headers=auth_header(owner),
    ).get_json()["id"]
    persist_reviews(
        client.application.extensions["database"],
        owner_id=owner,
        target_id=target_id,
        reviews=REVIEWS,
        skipped_count=0,
        source_kind="google_maps",
    )
    return target_id


def returning_session(auth_header, owner="user-a"):
    """A token minted for a later session (distinct expiry) for the same returning user."""
    # Sleep a beat so the expiry differs from any earlier token, representing a new login.
    time.sleep(1)
    return auth_header(owner, expires_in=7200)


def test_returning_user_reopens_name_source_and_ingestion_state(client, auth_header):
    target_id = create_and_ingest(client, auth_header)

    workspace = client.get(f"/api/targets/{target_id}", headers=returning_session(auth_header))

    assert workspace.status_code == 200
    body = workspace.get_json()
    assert body["name"] == "Joe's Coffee"  # (1) analysis name
    assert body["source_url"] == SOURCE_URL  # (2) source/entity context
    assert body["platform"] == "google_maps"
    assert body["latest_ingestion"]["status"] == "succeeded"  # (3) current ingestion state


def test_returning_user_reopens_the_current_review_dataset(client, auth_header):
    target_id = create_and_ingest(client, auth_header)

    reviews = client.get(
        f"/api/targets/{target_id}/reviews", headers=returning_session(auth_header)
    ).get_json()["reviews"]

    # (4) current persisted review dataset is restored in full.
    assert sorted(r["text"] for r in reviews) == ["Friendly staff", "Great coffee", "Too slow"]


def test_returning_user_reopens_the_ingestion_summary(client, auth_header):
    target_id = create_and_ingest(client, auth_header)

    summary = client.get(
        f"/api/targets/{target_id}/summary", headers=returning_session(auth_header)
    ).get_json()

    # (5) ingestion summary reflects the restored dataset.
    assert summary["review_count"] == 3
    assert summary["average_rating"] == round((5.0 + 2.0 + 4.0) / 3, 2)
    assert summary["latest_ingestion"]["status"] == "succeeded"


def test_reopened_dataset_is_unchanged_from_the_earlier_session(client, auth_header):
    target_id = create_and_ingest(client, auth_header)

    first = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a")).get_json()
    later = client.get(f"/api/targets/{target_id}", headers=returning_session(auth_header))

    # Reopening restores the same analysis; it does not create a new one or alter it.
    assert later.get_json()["id"] == first["id"] == target_id


def test_another_user_cannot_reopen_the_analysis(client, auth_header):
    target_id = create_and_ingest(client, auth_header)

    denied = client.get(f"/api/targets/{target_id}", headers=auth_header("user-b"))
    denied_summary = client.get(f"/api/targets/{target_id}/summary", headers=auth_header("user-b"))
    denied_reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-b"))

    assert denied.status_code == 404
    assert denied_summary.status_code == 404
    assert denied_reviews.status_code == 404
    assert b"Joe" not in denied.data


def test_expired_session_cannot_reopen(client, auth_header):
    target_id = create_and_ingest(client, auth_header)
    expired = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a", expires_in=-10))
    assert expired.status_code == 401
