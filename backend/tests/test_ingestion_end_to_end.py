import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.review_source_csv import RawReviewBatch
from app.models import IngestionRun, Review

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"


def make_target(client, auth_header, user="user-a"):
    response = client.post(
        "/api/targets",
        json={"name": "Coffee shop", "platform": "google_maps", "source_url": SOURCE_URL},
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


def test_owner_imports_real_supplied_reviews_and_workspace_reports_state(client, auth_header):
    target_id = make_target(client, auth_header)
    response = upload(
        client,
        auth_header("user-a"),
        target_id,
        b"review_text,rating\nGood coffee,5\n,4\nCold tea,2\n",
    )
    assert response.status_code == 201
    run = response.get_json()["run"]
    assert (run["status"], run["imported_count"], run["skipped_count"]) == ("partial", 2, 1)
    assert run["skip_reasons"] == {"missing_text": 1}
    workspace = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a"))
    assert workspace.get_json()["latest_ingestion"]["status"] == "partial"
    assert workspace.get_json()["latest_ingestion"]["skip_reasons"] == {"missing_text": 1}
    reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert reviews.status_code == 200
    assert sorted(x["text"] for x in reviews.get_json()["reviews"]) == ["Cold tea", "Good coffee"]


def test_failed_import_records_run_but_not_reviews(client, auth_header):
    target_id = make_target(client, auth_header)
    response = upload(client, auth_header("user-a"), target_id, b"review_text,rating\n,5\n")
    assert response.status_code == 422
    workspace = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a"))
    assert workspace.get_json()["latest_ingestion"]["status"] == "failed"
    reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert reviews.get_json()["reviews"] == []


def test_skipped_records_are_reported_and_never_enter_the_dataset(client, auth_header):
    target_id = make_target(client, auth_header)
    response = upload(
        client,
        auth_header("user-a"),
        target_id,
        b"review_text,rating\nGood coffee,5\n,4\nNo stars,\nToo many stars,9\n",
    )
    assert response.status_code == 201
    run = response.get_json()["run"]
    assert (run["total_count"], run["imported_count"], run["skipped_count"]) == (4, 1, 3)
    assert run["skip_reasons"] == {"invalid_rating": 2, "missing_text": 1}
    reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert [x["text"] for x in reviews.get_json()["reviews"]] == ["Good coffee"]
    summary = client.get(f"/api/targets/{target_id}/summary", headers=auth_header("user-a"))
    assert summary.status_code == 200
    # Skipped records must not count as analyzed data in the summary either.
    assert (summary.get_json()["review_count"], summary.get_json()["average_rating"]) == (1, 5.0)


def test_fully_rejected_import_still_reports_what_was_rejected(client, auth_header):
    target_id = make_target(client, auth_header)
    response = upload(
        client, auth_header("user-a"), target_id, b"review_text,rating\n,5\nNo stars,0\n"
    )
    assert response.status_code == 422
    latest = client.get(f"/api/targets/{target_id}", headers=auth_header("user-a")).get_json()[
        "latest_ingestion"
    ]
    assert latest["status"] == "failed"
    assert (latest["total_count"], latest["imported_count"], latest["skipped_count"]) == (2, 0, 2)
    assert latest["skip_reasons"] == {"invalid_rating": 1, "missing_text": 1}


def test_other_user_cannot_upload_or_retrieve_reviews(client, auth_header):
    target_id = make_target(client, auth_header, "user-a")
    response = upload(client, auth_header("user-b"), target_id, b"review_text,rating\nLeak,5\n")
    assert response.status_code == 404
    assert (
        client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-b")).status_code
        == 404
    )
    with Session(client.application.extensions["database"]) as session:
        assert session.scalars(select(Review)).all() == []
        assert session.scalars(select(IngestionRun)).all() == []


def test_real_source_batch_is_normalized_and_persisted(client, auth_header):
    target_id = make_target(client, auth_header)

    class FakeProvider:
        def submit(self, *, target_id, source_url):
            return RawReviewBatch(
                rows=[
                    {
                        "snippet": "Excellent",
                        "rating": 5,
                        "review_id": "g1",
                        "user": {"name": "Alex"},
                    }
                ],
                source_kind="serpapi_google_maps",
            )

    client.application.extensions["review_source"] = FakeProvider()
    response = client.post(f"/api/targets/{target_id}/ingestions", headers=auth_header("user-a"))
    assert response.status_code == 202
    assert response.get_json()["run_status"] == "succeeded"
    reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert reviews.get_json()["reviews"][0]["text"] == "Excellent"


def test_reingesting_saves_only_reviews_not_already_stored(client, auth_header):
    target_id = make_target(client, auth_header)
    batches = [["g1", "g2"], ["g2", "g3"]]

    class FakeProvider:
        def submit(self, *, target_id, source_url):
            ids = batches.pop(0)
            rows = [{"snippet": f"Review {i}", "rating": 4, "review_id": i} for i in ids]
            return RawReviewBatch(rows=rows, source_kind="serpapi_google_maps")

    client.application.extensions["review_source"] = FakeProvider()
    url = f"/api/targets/{target_id}/ingestions"
    assert client.post(url, headers=auth_header("user-a")).get_json()["imported_count"] == 2
    assert client.post(url, headers=auth_header("user-a")).get_json()["imported_count"] == 1
    reviews = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header("user-a"))
    assert sorted(x["source_review_id"] for x in reviews.get_json()["reviews"]) == [
        "g1",
        "g2",
        "g3",
    ]
