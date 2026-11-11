"""S2-016: another user's review data can never enter the AI context.

These tests go through the real HTTP endpoint (auth, routing, ownership, context
building) with two users and two datasets. The model is a recording fake, so each test
inspects exactly what would have been sent to Gemini instead of judging isolation from
generated prose.

User A's reviews contain a distinctive phrase that appears nowhere in User B's data.
If any part of User A's dataset reached User B's model call, that phrase would show up
in the captured context.
"""

import re

import pytest
from sqlalchemy.orm import Session

from app import create_app
from app.models import AnalysisTarget, Base
from app.services.review_storage import persist_reviews

SECRET = "test-secret-at-least-32-bytes-long!!"  # matches conftest.auth_header
SOURCE_URL = "https://www.google.com/maps/place/Example"
SECRET_PHRASE = "PURPLE-ELEPHANT-WAFFLE-7731"
REPLY = '{"status": "answered", "answer": "ok", "review_ids": []}'

USER_A_REVIEWS = [
    f"The {SECRET_PHRASE} special is the best thing on the menu.",
    f"I drove an hour for the {SECRET_PHRASE}. Worth it.",
    "Battery-powered candles on every table, cozy vibe.",
]
USER_B_REVIEWS = [
    "Customer service was slow but friendly.",
    "The staff fixed my order quickly.",
]


class RecordingGemini:
    """Fake model boundary: records every call and returns a fixed valid reply."""

    def __init__(self):
        self.calls = []

    def answer(self, *, system_prompt, user_content):
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content})
        return REPLY


def add_target(engine, *, owner_id, target_id, name, reviews):
    with Session(engine) as session, session.begin():
        session.add(
            AnalysisTarget(
                id=target_id,
                owner_id=owner_id,
                name=name,
                platform="google_maps",
                source_url=SOURCE_URL,
            )
        )
    persist_reviews(
        engine,
        owner_id=owner_id,
        target_id=target_id,
        source_kind="google_maps_csv",
        reviews=[{"text": text, "rating": 5} for text in reviews],
        skipped_count=0,
    )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    monkeypatch.setenv("SERPAPI_API_KEYS", "")
    app = create_app(
        {
            "TESTING": True,
            "JWT_SECRET": SECRET,
            "SUPABASE_URL": "https://test.supabase.co",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'isolation.db'}",
        }
    )
    gemini = RecordingGemini()
    app.extensions["gemini"] = gemini
    engine = app.extensions["database"]
    Base.metadata.create_all(engine)
    add_target(
        engine,
        owner_id="user-a",
        target_id="a-target",
        name="Waffle Palace",
        reviews=USER_A_REVIEWS,
    )
    add_target(
        engine,
        owner_id="user-b",
        target_id="b-target",
        name="Service Shack",
        reviews=USER_B_REVIEWS,
    )
    yield app.test_client(), gemini
    engine.dispose()


def ask(client, headers, target_id, body=None, query=""):
    return client.post(
        f"/api/targets/{target_id}/questions{query}",
        json=body if body is not None else {"question": f"Tell me about the {SECRET_PHRASE}."},
        headers=headers,
    )


def review_texts(user_content):
    return re.findall(r"<review [^>]*>(.*?)</review>", user_content)


# --- The main scenario from the story --------------------------------------------------


def test_user_b_probing_question_sends_only_user_b_reviews(setup, auth_header):
    client, gemini = setup
    # User B asks a question designed to pull out User A's distinctive content.
    response = ask(client, auth_header("user-b"), "b-target")

    assert response.status_code == 200
    assert len(gemini.calls) == 1
    call = gemini.calls[0]
    # Exactly User B's reviews were supplied, and nothing else.
    assert sorted(review_texts(call["user_content"])) == sorted(USER_B_REVIEWS)
    # The only place the phrase appears is the user's own question, never as review data.
    assert call["user_content"].count(SECRET_PHRASE) == 1
    assert "Waffle Palace" not in call["system_prompt"]
    assert "Service Shack" in call["system_prompt"]
    assert SECRET_PHRASE not in response.get_data(as_text=True)


def test_control_user_a_does_get_the_phrase_in_their_own_context(setup, auth_header):
    # Proves the probe above could detect a leak: the phrase does reach the model when the
    # rightful owner asks about their own target.
    client, gemini = setup
    assert ask(client, auth_header("user-a"), "a-target").status_code == 200
    assert sorted(review_texts(gemini.calls[0]["user_content"])) == sorted(USER_A_REVIEWS)


# --- Attempts to point the pipeline at User A's data -----------------------------------


def test_user_b_cannot_ask_about_user_a_target_by_id(setup, auth_header):
    client, gemini = setup
    response = ask(client, auth_header("user-b"), "a-target")

    assert response.status_code == 404
    # Rejected before the model is called, so nothing of User A's could be sent anywhere.
    assert gemini.calls == []
    assert SECRET_PHRASE not in response.get_data(as_text=True)
    assert "Waffle Palace" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "extra",
    [
        {"target_id": "a-target"},
        {"targetId": "a-target"},
        {"owner_id": "user-a"},
        {"user_id": "user-a"},
        {"reviews": [{"text": "injected", "rating": 5}]},
        {"context": "<reviews><review>injected</review></reviews>"},
    ],
)
def test_forged_body_fields_are_refused_before_the_model(setup, auth_header, extra):
    client, gemini = setup
    response = ask(
        client, auth_header("user-b"), "b-target", {"question": "Any complaints?", **extra}
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert gemini.calls == []


def test_forged_query_parameters_are_ignored(setup, auth_header):
    client, gemini = setup
    response = ask(
        client, auth_header("user-b"), "b-target", query="?target_id=a-target&owner_id=user-a"
    )

    assert response.status_code == 200
    assert sorted(review_texts(gemini.calls[0]["user_content"])) == sorted(USER_B_REVIEWS)


def test_unauthenticated_request_never_reaches_the_model(setup):
    client, gemini = setup
    response = client.post("/api/targets/a-target/questions", json={"question": "q"})
    assert response.status_code == 401
    assert gemini.calls == []


# --- No leak through shared state between requests -------------------------------------


@pytest.mark.parametrize("first", ["user-a", "user-b"])
def test_back_to_back_requests_from_two_users_stay_isolated(setup, auth_header, first):
    # Interleaved requests on one running app: nothing from one user's call can linger
    # into the other's (no shared session, cache, or "active target" state).
    client, gemini = setup
    order = [first, "user-b" if first == "user-a" else "user-a"]
    for user in order:
        target = "a-target" if user == "user-a" else "b-target"
        assert ask(client, auth_header(user), target).status_code == 200

    expected = {"user-a": USER_A_REVIEWS, "user-b": USER_B_REVIEWS}
    for user, call in zip(order, gemini.calls, strict=True):
        assert sorted(review_texts(call["user_content"])) == sorted(expected[user])
