"""S2-020: empty persisted datasets never reach Gemini.

The existing API returns 400 VALIDATION_ERROR for no reviews. Preserve that contract:
Sprint-2 integration tests already assert it and there is no need to change the API.
"""

from sqlalchemy.orm import Session

from app.models import AnalysisTarget
from app.services.review_storage import persist_reviews, record_failed_run


class SpyModel:
    def __init__(self):
        self.calls = []

    def answer(self, *, system_prompt, user_content):
        self.calls.append((system_prompt, user_content))
        return '{"status":"answered","answer":"Evidence only.","review_ids":[]}'


def make_target(engine):
    with Session(engine) as session, session.begin():
        session.add(
            AnalysisTarget(
                id="s2-empty",
                owner_id="user-a",
                name="Empty Cafe",
                platform="google_maps",
                source_url="https://www.google.com/maps/place/EmptyCafe",
            )
        )


def ask(client, headers):
    return client.post(
        "/api/targets/s2-empty/questions",
        json={"question": "How was the service?"},
        headers=headers,
    )


def test_no_ingestion_means_no_gemini_call(client, auth_header):
    engine = client.application.extensions["database"]
    make_target(engine)
    model = SpyModel()
    client.application.extensions["gemini"] = model
    response = ask(client, auth_header("user-a"))
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert "no reviews" in response.get_json()["error"]["message"].lower()
    assert model.calls == []


def test_failed_ingestion_without_reviews_does_not_invoke_model(client, auth_header):
    engine = client.application.extensions["database"]
    make_target(engine)
    record_failed_run(
        engine,
        owner_id="user-a",
        target_id="s2-empty",
        source_kind="serpapi_google_maps",
        message="Provider unavailable",
    )
    model = SpyModel()
    client.application.extensions["gemini"] = model
    assert ask(client, auth_header("user-a")).status_code == 400
    assert model.calls == []


def test_older_persisted_reviews_survive_a_later_failed_run(client, auth_header):
    engine = client.application.extensions["database"]
    make_target(engine)
    persist_reviews(
        engine,
        owner_id="user-a",
        target_id="s2-empty",
        reviews=[{"text": "The staff were great.", "rating": 5}],
        skipped_count=0,
        source_kind="google_maps_csv",
    )
    record_failed_run(
        engine,
        owner_id="user-a",
        target_id="s2-empty",
        source_kind="serpapi_google_maps",
        message="A later attempt failed",
    )
    model = SpyModel()
    client.application.extensions["gemini"] = model
    assert ask(client, auth_header("user-a")).status_code == 200
    assert len(model.calls) == 1
    assert "The staff were great" in model.calls[0][1]


def test_foreign_user_never_sees_empty_target_details(client, auth_header):
    engine = client.application.extensions["database"]
    make_target(engine)
    model = SpyModel()
    client.application.extensions["gemini"] = model
    assert ask(client, auth_header("user-b")).status_code == 404
    assert model.calls == []
