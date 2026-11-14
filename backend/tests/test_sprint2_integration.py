"""S2-002: integration tests across the Sprint 2 service boundaries.

Unit tests elsewhere prove each layer on its own (often by seeding the database
directly). These tests prove the layers agree when combined. Every test drives the real
HTTP stack: JWT auth -> routes -> services -> SQLAlchemy -> database. Review data enters
only through the real ingestion endpoints (CSV upload or a review-source batch), then is
read back through the reviews, summary, and Q&A endpoints.

Only the two external boundaries are faked:

- the review provider (``review_source``) returns a scripted ``RawReviewBatch``;
- Gemini is a ``RecordingGemini`` that stores every prompt it receives, so a test can
  check exactly which reviews would have reached the model.

Boundaries covered (ticket "representative areas"):

1. Loading persisted reviews for an AnalysisTarget.
2. Computing the ingestion summary from persisted data.
3. Passing the correct review dataset into the Q&A service.
4. Applying authenticated ownership before review retrieval.
5. Changing the active target and retrieving different data.
"""

import io
import json
import re

import pytest

from app.adapters.review_source_csv import RawReviewBatch

SOURCE_URL = "https://www.google.com/maps/place/Example"
REVIEW_ID = re.compile(r'<review id="([^"]+)"')


class RecordingGemini:
    """Fake model: records each call and answers by citing every review it was sent.

    ``extra_ids`` are added to the citation list to check that the service drops ids
    that were never part of the supplied context.
    """

    def __init__(self, extra_ids=()):
        self.calls = []
        self.extra_ids = list(extra_ids)

    def answer(self, *, system_prompt, user_content):
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content})
        ids = REVIEW_ID.findall(user_content) + self.extra_ids
        return json.dumps({"status": "answered", "answer": "From the reviews.", "review_ids": ids})

    def context_ids(self, call=-1):
        return REVIEW_ID.findall(self.calls[call]["user_content"])


class ScriptedProvider:
    """Fake review source: returns one queued batch of provider rows per ingestion."""

    def __init__(self, *batches):
        self.batches = list(batches)
        self.submitted = []

    def submit(self, *, target_id, source_url):
        self.submitted.append(target_id)
        return RawReviewBatch(rows=self.batches.pop(0), source_kind="serpapi_google_maps")


@pytest.fixture
def gemini(client):
    fake = RecordingGemini()
    client.application.extensions["gemini"] = fake
    return fake


# --- HTTP helpers ----------------------------------------------------------------------------


def create_target(client, headers, name):
    response = client.post(
        "/api/targets",
        json={"name": name, "platform": "google_maps", "source_url": SOURCE_URL},
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def upload_csv(client, headers, target_id, csv_text):
    return client.post(
        f"/api/targets/{target_id}/ingestions/import",
        headers=headers,
        data={"file": (io.BytesIO(csv_text.encode()), "reviews.csv")},
        content_type="multipart/form-data",
    )


def get_reviews(client, headers, target_id):
    response = client.get(f"/api/targets/{target_id}/reviews", headers=headers)
    assert response.status_code == 200
    return response.get_json()["reviews"]


def get_summary(client, headers, target_id):
    response = client.get(f"/api/targets/{target_id}/summary", headers=headers)
    assert response.status_code == 200
    return response.get_json()


def ask(client, headers, target_id, question="What do customers say?"):
    return client.post(
        f"/api/targets/{target_id}/questions", json={"question": question}, headers=headers
    )


# --- 1-3. One ingested dataset is what reviews, summary, and Q&A all see ----------------------


def test_csv_import_flows_into_reviews_summary_and_qa_context(client, auth_header, gemini):
    owner = auth_header("user-a")
    target_id = create_target(client, owner, "Corner Cafe")
    # Two valid rows plus one blank-text and one out-of-range row that must be skipped.
    response = upload_csv(
        client,
        owner,
        target_id,
        "review_text,rating\nGreat espresso,5\n,4\nSlow service,2\nBad rating,9\n",
    )
    assert response.status_code == 201
    run = response.get_json()["run"]
    assert (run["status"], run["imported_count"], run["skipped_count"]) == ("partial", 2, 2)

    reviews = get_reviews(client, owner, target_id)
    assert sorted(r["text"] for r in reviews) == ["Great espresso", "Slow service"]

    summary = get_summary(client, owner, target_id)
    assert summary["review_count"] == 2
    assert summary["average_rating"] == 3.5
    assert summary["rating_distribution"] == {"1": 0, "2": 1, "3": 0, "4": 0, "5": 1}
    assert summary["latest_ingestion"]["id"] == run["id"]

    answer = ask(client, owner, target_id)
    assert answer.status_code == 200
    body = answer.get_json()
    # The model received exactly the persisted reviews (same ids), and nothing skipped.
    persisted_ids = {r["id"] for r in reviews}
    assert set(gemini.context_ids()) == persisted_ids
    assert body["reviews_considered"] == summary["review_count"]
    assert "Bad rating" not in gemini.calls[-1]["user_content"]
    assert "Corner Cafe" in gemini.calls[-1]["system_prompt"]
    assert set(body["review_ids"]) == persisted_ids


def test_summary_reflects_all_persisted_runs_but_not_failed_or_duplicate_data(
    client, auth_header, gemini
):
    owner = auth_header("user-a")
    target_id = create_target(client, owner, "Corner Cafe")
    client.application.extensions["review_source"] = ScriptedProvider(
        [
            {"snippet": "Lovely staff", "rating": 5, "review_id": "g1"},
            {"snippet": "Too loud", "rating": 3, "review_id": "g2"},
        ],
        # The second provider run repeats g2; it must not be stored or counted twice.
        [
            {"snippet": "Too loud", "rating": 3, "review_id": "g2"},
            {"snippet": "Cold food", "rating": 1, "review_id": "g3"},
        ],
    )
    url = f"/api/targets/{target_id}/ingestions"
    assert client.post(url, headers=owner).get_json()["imported_count"] == 2
    assert client.post(url, headers=owner).get_json()["imported_count"] == 1

    summary = get_summary(client, owner, target_id)
    assert summary["review_count"] == 3
    assert summary["average_rating"] == 3.0
    assert summary["latest_ingestion"]["status"] == "succeeded"

    # A failed CSV import afterwards records a run but leaves the dataset unchanged.
    assert upload_csv(client, owner, target_id, "review_text,rating\n,5\n").status_code == 422
    after_failure = get_summary(client, owner, target_id)
    assert after_failure["review_count"] == 3
    assert after_failure["average_rating"] == 3.0
    assert after_failure["latest_ingestion"]["status"] == "failed"

    ask(client, owner, target_id)
    context_ids = gemini.context_ids()
    assert len(context_ids) == len(set(context_ids)) == 3
    assert set(context_ids) == {r["id"] for r in get_reviews(client, owner, target_id)}


def test_qa_drops_citations_that_are_not_in_the_persisted_dataset(client, auth_header):
    owner = auth_header("user-a")
    target_a = create_target(client, owner, "Cafe A")
    target_b = create_target(client, owner, "Cafe B")
    upload_csv(client, owner, target_a, "review_text,rating\nNice patio,4\n")
    upload_csv(client, owner, target_b, "review_text,rating\nNo parking,2\n")
    foreign_id = get_reviews(client, owner, target_b)[0]["id"]

    # The model also "cites" a real review id from another target and an invented id.
    fake = RecordingGemini(extra_ids=[foreign_id, "made-up-id"])
    client.application.extensions["gemini"] = fake
    body = ask(client, owner, target_a).get_json()

    assert body["review_ids"] == [get_reviews(client, owner, target_a)[0]["id"]]


def test_reviews_ingested_after_a_question_are_used_by_the_next_question(
    client, auth_header, gemini
):
    owner = auth_header("user-a")
    target_id = create_target(client, owner, "Corner Cafe")
    upload_csv(client, owner, target_id, "review_text,rating\nFirst visit was great,5\n")
    ask(client, owner, target_id)
    assert len(gemini.context_ids()) == 1

    upload_csv(client, owner, target_id, "review_text,rating\nSecond visit was worse,2\n")
    ask(client, owner, target_id)
    assert len(gemini.context_ids()) == 2
    assert "Second visit was worse" in gemini.calls[-1]["user_content"]
    assert get_summary(client, owner, target_id)["review_count"] == 2


# --- 4. Authenticated ownership is applied before any review retrieval ------------------------


def test_non_owner_gets_identical_not_found_and_no_review_data(client, auth_header, gemini):
    owner, intruder = auth_header("user-a"), auth_header("user-b")
    target_id = create_target(client, owner, "Corner Cafe")
    upload_csv(client, owner, target_id, "review_text,rating\nSecret menu item,5\n")

    for path in ("reviews", "summary"):
        foreign = client.get(f"/api/targets/{target_id}/{path}", headers=intruder)
        missing = client.get(f"/api/targets/does-not-exist/{path}", headers=intruder)
        assert foreign.status_code == missing.status_code == 404
        # Same body as a missing id, so the intruder can't tell the target exists.
        assert foreign.get_json() == missing.get_json()
        assert "Secret menu item" not in foreign.get_data(as_text=True)

    foreign = ask(client, intruder, target_id)
    missing = ask(client, intruder, "does-not-exist")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.get_json() == missing.get_json()
    # Ownership failed before review retrieval, so the model was never called.
    assert gemini.calls == []

    # The owner's data is untouched and still readable by the owner.
    assert get_summary(client, owner, target_id)["review_count"] == 1


def test_non_owner_cannot_ingest_into_or_change_another_users_dataset(client, auth_header):
    owner, intruder = auth_header("user-a"), auth_header("user-b")
    target_id = create_target(client, owner, "Corner Cafe")
    upload_csv(client, owner, target_id, "review_text,rating\nGenuine review,4\n")
    provider = ScriptedProvider([{"snippet": "Injected", "rating": 1, "review_id": "x"}])
    client.application.extensions["review_source"] = provider

    assert (
        upload_csv(client, intruder, target_id, "review_text,rating\nFake,1\n").status_code == 404
    )
    assert client.post(f"/api/targets/{target_id}/ingestions", headers=intruder).status_code == 404
    # The ownership check runs before the provider is called at all.
    assert provider.submitted == []

    summary = get_summary(client, owner, target_id)
    assert (summary["review_count"], summary["average_rating"]) == (1, 4.0)
    assert [r["text"] for r in get_reviews(client, owner, target_id)] == ["Genuine review"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "reviews"), ("get", "summary"), ("post", "questions")],
)
def test_unauthenticated_requests_never_reach_review_data(
    client, auth_header, gemini, method, path
):
    owner = auth_header("user-a")
    target_id = create_target(client, owner, "Corner Cafe")
    upload_csv(client, owner, target_id, "review_text,rating\nPrivate review,5\n")

    bad_token = auth_header("user-a", secret="wrong-secret-that-is-at-least-32-bytes")
    for headers in ({}, bad_token):
        response = getattr(client, method)(
            f"/api/targets/{target_id}/{path}", json={"question": "Hi?"}, headers=headers
        )
        assert response.status_code == 401
        assert "Private review" not in response.get_data(as_text=True)
    assert gemini.calls == []


# --- 5. Changing the active target retrieves different data ----------------------------------


def test_switching_targets_switches_reviews_summary_and_qa_context(client, auth_header, gemini):
    owner = auth_header("user-a")
    bakery = create_target(client, owner, "Sunrise Bakery")
    garage = create_target(client, owner, "Quick Lube Garage")
    upload_csv(client, owner, bakery, "review_text,rating\nFresh croissants,5\nTiny seating,4\n")
    upload_csv(client, owner, garage, "review_text,rating\nOverpriced oil change,1\n")
    bakery_ids = {r["id"] for r in get_reviews(client, owner, bakery)}
    garage_ids = {r["id"] for r in get_reviews(client, owner, garage)}
    assert bakery_ids.isdisjoint(garage_ids)

    # Simulate a user flipping between targets: bakery -> garage -> bakery.
    expected = [
        (bakery, "Sunrise Bakery", bakery_ids, 2, 4.5),
        (garage, "Quick Lube Garage", garage_ids, 1, 1.0),
        (bakery, "Sunrise Bakery", bakery_ids, 2, 4.5),
    ]
    for target_id, name, ids, count, average in expected:
        summary = get_summary(client, owner, target_id)
        assert (summary["target_id"], summary["review_count"]) == (target_id, count)
        assert summary["average_rating"] == average
        assert {r["id"] for r in get_reviews(client, owner, target_id)} == ids

        assert ask(client, owner, target_id).status_code == 200
        call = gemini.calls[-1]
        assert set(gemini.context_ids()) == ids
        assert f'"{name}"' in call["system_prompt"]
        other = "Quick Lube Garage" if name == "Sunrise Bakery" else "Sunrise Bakery"
        assert other not in call["system_prompt"] + call["user_content"]

    assert len(gemini.calls) == 3


def test_switching_to_a_target_without_reviews_does_not_reuse_previous_data(
    client, auth_header, gemini
):
    owner = auth_header("user-a")
    full = create_target(client, owner, "Busy Diner")
    empty = create_target(client, owner, "New Taqueria")
    upload_csv(client, owner, full, "review_text,rating\nGreat pancakes,5\n")

    assert ask(client, owner, full).status_code == 200
    calls_before = len(gemini.calls)

    # The empty target must not fall back to the previously viewed target's reviews.
    assert get_reviews(client, owner, empty) == []
    summary = get_summary(client, owner, empty)
    assert summary["review_count"] == 0
    assert summary["average_rating"] is None
    assert summary["latest_ingestion"] is None
    response = ask(client, owner, empty)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert len(gemini.calls) == calls_before

    # Once it has its own data, Q&A uses only that data.
    upload_csv(client, owner, empty, "review_text,rating\nBest al pastor in town,5\n")
    assert ask(client, owner, empty).status_code == 200
    assert "Best al pastor in town" in gemini.calls[-1]["user_content"]
    assert "Great pancakes" not in gemini.calls[-1]["user_content"]
