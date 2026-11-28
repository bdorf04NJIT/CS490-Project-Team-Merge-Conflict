"""S3-009: re-ingest (refresh) an existing analysis.

A refresh runs ingestion again on the same AnalysisTarget. It must not need a second
target, must be recorded as its own ingestion run, and must merge newly fetched reviews
into the existing dataset: reviews already collected stay current even when a later,
partial or throttled response leaves them out. The provider here is a scripted fake, so
no test calls SerpApi.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.review_source_csv import RawReviewBatch
from app.errors import IngestionUnavailable
from app.models import AnalysisTarget, IngestionRun, Review

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"


class ScriptedProvider:
    """Returns one scripted batch per refresh: a list of review ids, or an exception."""

    def __init__(self, *batches):
        self.batches = list(batches)

    def submit(self, *, target_id, source_url):
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        rows = [
            {"snippet": f"Review {review_id}", "rating": 4, "review_id": review_id}
            for review_id in batch
        ]
        return RawReviewBatch(rows=rows, source_kind="serpapi_google_maps")


def make_target(client, auth_header, user="user-a"):
    response = client.post(
        "/api/targets",
        json={"name": "Coffee shop", "platform": "google_maps", "source_url": SOURCE_URL},
        headers=auth_header(user),
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def refresh(client, auth_header, target_id, user="user-a"):
    return client.post(f"/api/targets/{target_id}/ingestions", headers=auth_header(user))


def saved_ids(client, auth_header, target_id):
    body = client.get(f"/api/targets/{target_id}/reviews", headers=auth_header()).get_json()
    return sorted(review["source_review_id"] for review in body["reviews"])


def db(client):
    return Session(client.application.extensions["database"])


def test_refresh_reuses_the_same_analysis_and_records_a_new_run(client, auth_header):
    target_id = make_target(client, auth_header)
    client.application.extensions["review_source"] = ScriptedProvider(["g1", "g2"], ["g3"])

    assert refresh(client, auth_header, target_id).status_code == 202
    assert refresh(client, auth_header, target_id).status_code == 202

    with db(client) as session:
        # No second AnalysisTarget was needed to get newer data.
        assert session.scalar(select(func.count(AnalysisTarget.id))) == 1
        runs = session.scalars(select(IngestionRun).where(IngestionRun.target_id == target_id))
        assert [run.imported_count for run in sorted(runs, key=lambda r: r.started_at)] == [2, 1]
        # Each review remembers which run brought it in, so attempts stay distinguishable.
        run_ids = set(session.scalars(select(Review.ingestion_run_id)))
        assert len(run_ids) == 2


def test_refresh_reports_new_already_saved_and_current_dataset_counts(client, auth_header):
    target_id = make_target(client, auth_header)
    client.application.extensions["review_source"] = ScriptedProvider(
        ["g1", "g2", "g3"], ["g2", "g3", "g4", "g5"]
    )

    first = refresh(client, auth_header, target_id).get_json()
    assert (first["imported_count"], first["already_saved_count"], first["review_count"]) == (
        3,
        0,
        3,
    )
    second = refresh(client, auth_header, target_id).get_json()
    assert (second["imported_count"], second["already_saved_count"], second["review_count"]) == (
        2,
        2,
        5,
    )


def test_partial_or_throttled_refresh_keeps_reviews_it_did_not_return(client, auth_header):
    # The second response only contains one old review and one new one, as a throttled
    # provider might return. The other previously collected reviews must remain current.
    target_id = make_target(client, auth_header)
    client.application.extensions["review_source"] = ScriptedProvider(
        ["g1", "g2", "g3", "g4"], ["g4", "g5"]
    )

    refresh(client, auth_header, target_id)
    body = refresh(client, auth_header, target_id).get_json()

    assert body["review_count"] == 5
    assert saved_ids(client, auth_header, target_id) == ["g1", "g2", "g3", "g4", "g5"]


def test_refresh_with_nothing_new_succeeds_and_changes_nothing(client, auth_header):
    target_id = make_target(client, auth_header)
    client.application.extensions["review_source"] = ScriptedProvider(["g1", "g2"], ["g1", "g2"])

    refresh(client, auth_header, target_id)
    body = refresh(client, auth_header, target_id).get_json()

    assert body["run_status"] == "succeeded"
    assert (body["imported_count"], body["already_saved_count"], body["review_count"]) == (0, 2, 2)
    assert saved_ids(client, auth_header, target_id) == ["g1", "g2"]


def test_failed_refresh_keeps_the_existing_dataset(client, auth_header):
    target_id = make_target(client, auth_header)
    client.application.extensions["review_source"] = ScriptedProvider(
        ["g1", "g2"], IngestionUnavailable()
    )

    refresh(client, auth_header, target_id)
    assert refresh(client, auth_header, target_id).status_code == 503

    assert saved_ids(client, auth_header, target_id) == ["g1", "g2"]
    workspace = client.get(f"/api/targets/{target_id}", headers=auth_header()).get_json()
    assert workspace["review_count"] == 2
    assert workspace["latest_ingestion"]["status"] == "failed"


def test_workspace_reports_the_current_dataset_size(client, auth_header):
    target_id = make_target(client, auth_header)
    url = f"/api/targets/{target_id}"
    assert client.get(url, headers=auth_header()).get_json()["review_count"] == 0

    client.application.extensions["review_source"] = ScriptedProvider(["g1", "g2"], ["g2", "g3"])
    refresh(client, auth_header, target_id)
    refresh(client, auth_header, target_id)

    workspace = client.get(url, headers=auth_header()).get_json()
    assert workspace["review_count"] == 3
    assert workspace["latest_ingestion"]["already_saved_count"] == 1


def test_another_user_cannot_refresh_the_analysis(client, auth_header):
    target_id = make_target(client, auth_header)
    provider = ScriptedProvider(["g1"])
    client.application.extensions["review_source"] = provider

    response = refresh(client, auth_header, target_id, user="user-b")

    assert response.status_code == 404
    assert provider.batches == [["g1"]]  # the provider was never called
    with db(client) as session:
        assert session.scalars(select(IngestionRun)).all() == []
