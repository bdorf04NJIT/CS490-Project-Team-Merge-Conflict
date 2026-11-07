"""S2-013: Review Q&A wires the system prompt + persisted reviews to Gemini.

Service tests use an in-memory database and a fake Gemini (a plain object with an
``answer`` method), so the model is never called. They prove the service reads the
owner-scoped persisted reviews, builds a user turn containing those reviews, rejects a
missing question, and maps a malformed model reply to a transient QaUnavailable rather
than a 500. The adapter's own construction guards and the HTTP boundary are covered too.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.adapters.gemini_source import GeminiReviewAnswerer, UnconfiguredGemini
from app.errors import NotFound, QaUnavailable, ValidationError
from app.models import Base
from app.services.review_qa import _question, _reviews_block, answer_question
from app.services.review_storage import persist_reviews

# Must match the secret the auth_header fixture signs tokens with (tests/conftest.py).
SECRET = "test-secret-at-least-32-bytes-long!!"

SOURCE_URL = "https://www.google.com/maps/place/Coffee+Shop"


class FakeGemini:
    """Stands in for the Gemini adapter: returns a scripted reply and records the call."""

    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    def answer(self, *, system_prompt, user_content):
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content})
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


@pytest.fixture
def engine():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def make_target(engine, *, owner_id="user-a", target_id="a"):
    from app.models import AnalysisTarget

    with Session(engine) as session, session.begin():
        session.add(
            AnalysisTarget(
                id=target_id,
                owner_id=owner_id,
                name=target_id.upper(),
                platform="google_maps",
                source_url=SOURCE_URL,
            )
        )
    return target_id


def seed(engine, target_id, ratings, *, owner_id="user-a"):
    persist_reviews(
        engine,
        owner_id=owner_id,
        target_id=target_id,
        source_kind="google_maps_csv",
        reviews=[{"text": f"review {i}", "rating": r} for i, r in enumerate(ratings)],
        skipped_count=0,
    )


# --- _question validation ------------------------------------------------------------------


def test_question_returns_trimmed_text():
    assert _question({"question": "  How is the coffee?  "}) == "How is the coffee?"


@pytest.mark.parametrize(
    "payload", [None, {}, {"question": ""}, {"question": "   "}, {"question": 5}]
)
def test_blank_or_missing_question_is_rejected(payload):
    with pytest.raises(ValidationError) as exc:
        _question(payload)
    assert exc.value.fields == {"question": "required"}


# --- _reviews_block renders and escapes ----------------------------------------------------


def test_reviews_block_renders_each_review_with_id_and_rating(engine):
    make_target(engine)
    seed(engine, "a", [5, 3])
    with Session(engine) as session:
        from app.services.review_summary import active_reviews

        reviews = session.scalars(active_reviews(owner_id="user-a", target_id="a")).all()
    block = _reviews_block(reviews)
    assert block.startswith("<reviews>")
    assert block.endswith("</reviews>")
    assert block.count("<review ") == 2
    assert 'rating="5.0"' in block and 'rating="3.0"' in block


def test_reviews_block_escapes_html_in_review_text(engine):
    make_target(engine)
    with Session(engine) as session, session.begin():
        from app.models import IngestionRun, Review

        run = IngestionRun(
            target_id="a", source_kind="google_maps_csv", status="succeeded", total_count=1
        )
        session.add(run)
        session.flush()
        session.add(Review(target_id="a", ingestion_run_id=run.id, text="<script>&bad", rating=4))
    with Session(engine) as session:
        from app.services.review_summary import active_reviews

        reviews = session.scalars(active_reviews(owner_id="user-a", target_id="a")).all()
    block = _reviews_block(reviews)
    assert "<script>" not in block
    assert "&lt;script&gt;&amp;bad" in block


# --- answer_question happy path and failure mapping ----------------------------------------


def test_answer_question_returns_parsed_reply_and_passes_reviews_to_model(engine):
    make_target(engine)
    seed(engine, "a", [5, 2])
    gemini = FakeGemini('{"status": "answered", "answer": "Good coffee.", "review_ids": ["1"]}')

    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": "How is it?"}
    )

    assert result == {"status": "answered", "answer": "Good coffee.", "review_ids": ["1"]}
    # The model received the question and a reviews block built from persisted reviews.
    assert len(gemini.calls) == 1
    user_content = gemini.calls[0]["user_content"]
    assert "Question: How is it?" in user_content
    assert "<reviews>" in user_content and user_content.count("<review ") == 2


def test_answer_question_defaults_review_ids_when_model_omits_them(engine):
    make_target(engine)
    seed(engine, "a", [4])
    gemini = FakeGemini('{"status": "answered", "answer": "Fine."}')
    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"}
    )
    assert result["review_ids"] == []


def test_missing_question_raises_before_touching_the_model(engine):
    make_target(engine)
    seed(engine, "a", [5])
    gemini = FakeGemini("unused")
    with pytest.raises(ValidationError):
        answer_question(engine, gemini, owner_id="user-a", target_id="a", payload={})
    assert gemini.calls == []


def test_target_with_no_reviews_is_rejected_without_calling_model(engine):
    make_target(engine)
    gemini = FakeGemini("unused")
    with pytest.raises(ValidationError) as exc:
        answer_question(engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"})
    assert "no reviews" in str(exc.value).lower()
    assert gemini.calls == []


def test_foreign_or_missing_target_raises_not_found(engine):
    make_target(engine, owner_id="user-b", target_id="c")
    seed(engine, "c", [5], owner_id="user-b")
    gemini = FakeGemini("unused")
    with pytest.raises(NotFound):
        answer_question(engine, gemini, owner_id="user-a", target_id="c", payload={"question": "q"})
    assert gemini.calls == []


def test_non_json_model_reply_maps_to_qa_unavailable(engine):
    make_target(engine)
    seed(engine, "a", [5])
    gemini = FakeGemini("not json at all")
    with pytest.raises(QaUnavailable):
        answer_question(engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"})


def test_json_array_reply_maps_to_qa_unavailable(engine):
    make_target(engine)
    seed(engine, "a", [5])
    gemini = FakeGemini('["not", "an", "object"]')
    with pytest.raises(QaUnavailable):
        answer_question(engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"})


# --- Adapter construction guards -----------------------------------------------------------


def test_unconfigured_gemini_reports_not_configured():
    with pytest.raises(QaUnavailable) as exc:
        UnconfiguredGemini().answer(system_prompt="s", user_content="u")
    assert "not configured" in str(exc.value).lower()


def test_gemini_requires_an_api_key():
    with pytest.raises(ValueError):
        GeminiReviewAnswerer("")


def test_pinned_model_uses_only_that_model():
    a = GeminiReviewAnswerer("key", model="gemini-3.5-flash")
    assert a._models == ("gemini-3.5-flash",)


def test_default_chain_used_without_a_pinned_model():
    from app.adapters.gemini_source import FALLBACK_MODELS

    assert GeminiReviewAnswerer("key")._models == FALLBACK_MODELS


# --- HTTP boundary: POST /api/targets/<id>/questions ---------------------------------------


@pytest.fixture
def qa_client(tmp_path, monkeypatch):
    """Test client whose Gemini extension is a FakeGemini, so no model is called."""
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    monkeypatch.setenv("SERPAPI_API_KEYS", "")

    def _build(reply):
        app = create_app(
            {
                "TESTING": True,
                "JWT_SECRET": SECRET,
                "SUPABASE_URL": "https://test.supabase.co",
                "DATABASE_URL": f"sqlite:///{tmp_path / 'qa.db'}",
            }
        )
        # setdefault in create_app means a pre-seeded extension would win, but the app is
        # already built here; override directly before the request is handled.
        app.extensions["gemini"] = FakeGemini(reply)
        engine = app.extensions["database"]
        Base.metadata.create_all(engine)
        make_target(engine)
        seed(engine, "a", [5, 1])
        return app

    return _build


def test_owner_can_ask_a_question_over_api(qa_client, auth_header):
    app = qa_client('{"status": "answered", "answer": "Mixed.", "review_ids": []}')
    client = app.test_client()
    response = client.post(
        "/api/targets/a/questions",
        json={"question": "Summarize the reviews"},
        headers=auth_header("user-a"),
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "answered", "answer": "Mixed.", "review_ids": []}


def test_question_requires_authentication(qa_client):
    app = qa_client('{"status": "answered", "answer": "x", "review_ids": []}')
    client = app.test_client()
    response = client.post("/api/targets/a/questions", json={"question": "q"})
    assert response.status_code == 401


def test_other_user_cannot_ask_about_a_target(qa_client, auth_header):
    app = qa_client('{"status": "answered", "answer": "x", "review_ids": []}')
    client = app.test_client()
    response = client.post(
        "/api/targets/a/questions", json={"question": "q"}, headers=auth_header("user-b")
    )
    assert response.status_code == 404


def test_blank_question_rejected_over_api(qa_client, auth_header):
    app = qa_client('{"status": "answered", "answer": "x", "review_ids": []}')
    client = app.test_client()
    response = client.post(
        "/api/targets/a/questions", json={"question": "   "}, headers=auth_header("user-a")
    )
    assert response.status_code == 400
