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
from app.services.qa_prompt import build_system_prompt
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


def seed_reviews(engine, target_id, specs, *, owner_id="user-a"):
    """Insert reviews with explicit id/created_at/text so order and size are controllable.

    ``specs`` is a list of dicts with keys: id, text, rating, created_at (datetime).
    Bypasses persist_reviews so the test can set created_at (persist_reviews stamps now).
    """
    from datetime import UTC, datetime

    from app.models import IngestionRun, Review

    with Session(engine) as session, session.begin():
        run = IngestionRun(
            target_id=target_id,
            source_kind="google_maps_csv",
            status="succeeded",
            total_count=len(specs),
        )
        session.add(run)
        session.flush()
        for spec in specs:
            session.add(
                Review(
                    id=spec["id"],
                    target_id=target_id,
                    ingestion_run_id=run.id,
                    text=spec.get("text", "x"),
                    rating=spec.get("rating", 5),
                    created_at=spec.get("created_at", datetime.now(UTC)),
                )
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
    block, _ = _reviews_block(reviews)
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
    block, _ = _reviews_block(reviews)
    assert "<script>" not in block
    assert "&lt;script&gt;&amp;bad" in block


# --- answer_question happy path and failure mapping ----------------------------------------


def test_answer_question_returns_parsed_reply_and_passes_reviews_to_model(engine):
    make_target(engine)
    seed_reviews(
        engine, "a", [{"id": "r1", "text": "Good coffee", "rating": 5}, {"id": "r2", "rating": 2}]
    )
    gemini = FakeGemini('{"status": "answered", "answer": "Good coffee.", "review_ids": ["r1"]}')

    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": "How is it?"}
    )

    assert result == {
        "status": "answered",
        "answer": "Good coffee.",
        "review_ids": ["r1"],
        "reviews_considered": 2,
    }
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
    assert response.get_json() == {
        "status": "answered",
        "answer": "Mixed.",
        "review_ids": [],
        "reviews_considered": 2,
    }


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


# --- S2-010: bounded, deterministic, scoped review context ---------------------------------


def _review_ids_in(user_content):
    import re

    return re.findall(r'<review id="([^"]+)"', user_content)


def test_context_is_capped_to_max_reviews_newest_first(engine):
    from datetime import UTC, datetime

    make_target(engine)
    # Five reviews with increasing created_at; r5 is newest, r1 oldest.
    seed_reviews(
        engine,
        "a",
        [
            {
                "id": f"r{i}",
                "text": f"text {i}",
                "rating": 5,
                "created_at": datetime(2026, 1, i, tzinfo=UTC),
            }
            for i in range(1, 6)
        ],
    )
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(
        engine,
        gemini,
        owner_id="user-a",
        target_id="a",
        payload={"question": "q"},
        max_reviews=3,
        max_context_chars=10_000,
    )

    ids = _review_ids_in(gemini.calls[0]["user_content"])
    # Only the 3 newest, newest-first, and never more than the cap.
    assert ids == ["r5", "r4", "r3"]


def test_context_is_bounded_by_character_budget(engine):
    from datetime import UTC, datetime

    make_target(engine)
    # Each review text is 100 chars; a 250-char budget fits the first plus one more.
    seed_reviews(
        engine,
        "a",
        [
            {
                "id": f"r{i}",
                "text": "x" * 100,
                "rating": 5,
                "created_at": datetime(2026, 1, i, tzinfo=UTC),
            }
            for i in range(1, 6)
        ],
    )
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(
        engine,
        gemini,
        owner_id="user-a",
        target_id="a",
        payload={"question": "q"},
        max_reviews=100,
        max_context_chars=250,
    )

    ids = _review_ids_in(gemini.calls[0]["user_content"])
    # Newest first: r5 (100) then r4 (200) fit; r3 would reach 300 > 250, so stop.
    assert ids == ["r5", "r4"]


def test_character_budget_always_includes_at_least_one_review(engine):
    make_target(engine)
    seed_reviews(engine, "a", [{"id": "r1", "text": "y" * 500, "rating": 4}])
    block, sent_ids = _reviews_block_from(engine)
    # A single oversized review is still included so the block is never empty.
    assert 'id="r1"' in block
    assert sent_ids == ["r1"]


def _reviews_block_from(engine):
    from app.services.review_qa import _reviews_block
    from app.services.review_summary import qa_context_reviews

    with Session(engine) as session:
        reviews = session.scalars(
            qa_context_reviews(owner_id="user-a", target_id="a", limit=100)
        ).all()
    return _reviews_block(reviews, max_chars=10)


def test_cap_never_leaks_another_users_reviews(engine):
    # user-a owns target "a"; user-b owns target "b" with its own reviews.
    make_target(engine, owner_id="user-a", target_id="a")
    make_target(engine, owner_id="user-b", target_id="b")
    seed(engine, "a", [5, 5], owner_id="user-a")
    seed(engine, "b", [1, 1, 1], owner_id="user-b")
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(
        engine,
        gemini,
        owner_id="user-a",
        target_id="a",
        payload={"question": "q"},
        max_reviews=100,
    )

    # Only target a's two reviews appear; none of target b's reviews leak in.
    user_content = gemini.calls[0]["user_content"]
    assert user_content.count("<review ") == 2


def test_qa_context_reviews_is_owner_and_target_scoped(engine):
    from app.services.review_summary import qa_context_reviews

    make_target(engine, owner_id="user-a", target_id="a")
    seed(engine, "a", [5, 4, 3], owner_id="user-a")

    with Session(engine) as session:
        # Foreign owner sees nothing even though the target id is valid.
        foreign = session.scalars(
            qa_context_reviews(owner_id="user-b", target_id="a", limit=100)
        ).all()
        owned = session.scalars(
            qa_context_reviews(owner_id="user-a", target_id="a", limit=100)
        ).all()
    assert foreign == []
    assert len(owned) == 3


# --- S2-003: deterministic Q&A test harness (the model boundary) ---------------------------
#
# These tests prove the harness can verify exactly what crosses the model boundary without
# any live-model call. The FakeGemini stub records the single ``answer(system_prompt,
# user_content)`` call, so each assertion below inspects what the application *sends* to the
# model and how it behaves on a *controlled* reply.


def test_system_instructions_sent_to_model_match_the_built_prompt(engine):
    # The exact system instruction the model receives must be the ReviewLens prompt built
    # for this target, not a hardcoded or stale string.
    make_target(engine, owner_id="user-a", target_id="a")
    seed(engine, "a", [5])
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"})

    sent_system_prompt = gemini.calls[0]["system_prompt"]
    expected = build_system_prompt(target_name="A", platform="google_maps")
    assert sent_system_prompt == expected


def test_system_instructions_carry_this_targets_name_and_platform(engine):
    # Two targets owned by the same user must each get system instructions naming only
    # themselves, so the model is never told about the wrong business.
    make_target(engine, owner_id="user-a", target_id="cafe")
    seed(engine, "cafe", [5])
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(engine, gemini, owner_id="user-a", target_id="cafe", payload={"question": "q"})

    sent_system_prompt = gemini.calls[0]["system_prompt"]
    assert 'Business: "CAFE"' in sent_system_prompt
    assert "Review platform: Google Maps" in sent_system_prompt


def test_wrong_target_reviews_are_not_supplied_to_the_model(engine):
    # Same owner, two targets. A question about target "a" must send only target "a"'s
    # reviews to the model, never the other target's reviews.
    make_target(engine, owner_id="user-a", target_id="a")
    make_target(engine, owner_id="user-a", target_id="b")
    seed(engine, "a", [5, 5], owner_id="user-a")
    seed(engine, "b", [1, 1, 1], owner_id="user-a")
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(
        engine,
        gemini,
        owner_id="user-a",
        target_id="a",
        payload={"question": "q"},
        max_reviews=100,
    )

    # Only target a's two reviews reach the model; none of target b's three reviews do.
    user_content = gemini.calls[0]["user_content"]
    assert user_content.count("<review ") == 2


def test_cross_user_reviews_are_not_supplied_to_the_model(engine):
    # Two users each own a target. A question from user-a must send only user-a's reviews
    # to the model, never user-b's, even though the fake model would accept anything.
    make_target(engine, owner_id="user-a", target_id="shared")
    make_target(engine, owner_id="user-b", target_id="other")
    seed(engine, "shared", [5, 5], owner_id="user-a")
    seed(engine, "other", [1, 1, 1], owner_id="user-b")
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": []}')

    answer_question(
        engine,
        gemini,
        owner_id="user-a",
        target_id="shared",
        payload={"question": "q"},
        max_reviews=100,
    )

    user_content = gemini.calls[0]["user_content"]
    assert user_content.count("<review ") == 2


def test_controlled_insufficient_evidence_reply_is_passed_through(engine):
    # Application behavior must follow a controlled model response: an insufficient-evidence
    # status is surfaced verbatim, not treated as an error.
    make_target(engine)
    seed(engine, "a", [5])
    gemini = FakeGemini(
        '{"status": "insufficient_evidence", "answer": "The reviews do not say.", "review_ids": []}'
    )

    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"}
    )

    assert result == {
        "status": "insufficient_evidence",
        "answer": "The reviews do not say.",
        "review_ids": [],
        "reviews_considered": 1,
    }


def test_controlled_out_of_scope_reply_is_passed_through(engine):
    # A controlled out-of-scope decline is surfaced as-is.
    make_target(engine)
    seed(engine, "a", [5])
    gemini = FakeGemini(
        '{"status": "out_of_scope", "answer": "I can only answer about these reviews.",'
        ' "review_ids": []}'
    )

    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"}
    )

    assert result["status"] == "out_of_scope"
    assert result["review_ids"] == []


def test_model_boundary_is_called_exactly_once_per_question(engine):
    # The harness can prove the orchestrator makes a single model call per question, so
    # CI never fans out into repeated (paid) requests.
    make_target(engine)
    seed(engine, "a", [5, 4])
    gemini = FakeGemini('{"status": "answered", "answer": "ok", "review_ids": ["0"]}')

    answer_question(engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"})

    assert len(gemini.calls) == 1


# --- S2-011: answers stay tied to the supplied review evidence -----------------------------
#
# A small controlled dataset where the right answer is known: two reviews complain about
# slow service, two praise the food, one is unrelated. The fake model plays back the kind
# of reply real Gemini gives; the tests prove the application keeps only citations of
# reviews that were actually supplied and rejects replies that break the format.

PIO_PIO_REVIEWS = [
    {"id": "slow-1", "rating": 2, "text": "Food was great but we waited 40 minutes."},
    {"id": "slow-2", "rating": 1, "text": "Service was so slow, staff ignored us."},
    {"id": "food-1", "rating": 5, "text": "Best rotisserie chicken in the city!"},
    {"id": "food-2", "rating": 5, "text": "The green sauce is amazing."},
    {"id": "other-1", "rating": 4, "text": "Nice decor and music."},
]


def ask(engine, reply, question="What do customers complain about?", **kwargs):
    make_target(engine)
    seed_reviews(engine, "a", PIO_PIO_REVIEWS)
    gemini = FakeGemini(reply)
    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": question}, **kwargs
    )
    return result, gemini


def test_supported_answer_cites_the_reviews_it_is_based_on(engine):
    result, gemini = ask(
        engine,
        '{"status": "answered", "answer": "Two reviewers complain about slow service.",'
        ' "review_ids": ["slow-1", "slow-2"]}',
    )

    assert result == {
        "status": "answered",
        "answer": "Two reviewers complain about slow service.",
        "review_ids": ["slow-1", "slow-2"],
        "reviews_considered": 5,
    }
    # Every review in the dataset was supplied as evidence, so the model saw them all.
    user_content = gemini.calls[0]["user_content"]
    for review in PIO_PIO_REVIEWS:
        assert f'id="{review["id"]}"' in user_content


def test_invented_review_ids_are_removed_from_the_evidence(engine):
    result, _ = ask(
        engine,
        '{"status": "answered", "answer": "Service is slow.",'
        ' "review_ids": ["slow-1", "made-up", "slow-2"]}',
    )

    assert result["review_ids"] == ["slow-1", "slow-2"]


def test_review_ids_are_deduplicated_and_returned_as_strings(engine):
    make_target(engine)
    seed_reviews(engine, "a", [{"id": "7", "text": "slow"}, {"id": "9", "text": "slow too"}])
    gemini = FakeGemini('{"status": "answered", "answer": "Slow.", "review_ids": [7, "7", "9"]}')

    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="a", payload={"question": "q"}
    )

    assert result["review_ids"] == ["7", "9"]


def test_review_left_out_by_the_context_budget_cannot_be_cited(engine):
    # The character budget only fits the newest review, so the older one is never sent.
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    make_target(engine)
    seed_reviews(
        engine,
        "a",
        [
            {"id": "new", "text": "slow service", "created_at": now},
            {"id": "old", "text": "slow service again", "created_at": now - timedelta(days=1)},
        ],
    )
    gemini = FakeGemini('{"status": "answered", "answer": "Slow.", "review_ids": ["new", "old"]}')

    result = answer_question(
        engine,
        gemini,
        owner_id="user-a",
        target_id="a",
        payload={"question": "q"},
        max_context_chars=15,
    )

    assert result["review_ids"] == ["new"]
    assert result["reviews_considered"] == 1


def test_answer_whose_citations_are_all_invalid_is_kept_without_evidence(engine):
    result, _ = ask(
        engine,
        '{"status": "answered", "answer": "Service is slow.", "review_ids": ["nope", 3]}',
    )

    assert result["status"] == "answered"
    assert result["answer"] == "Service is slow."
    assert result["review_ids"] == []


@pytest.mark.parametrize("review_ids", ['"slow-1"', "null", '{"id": "slow-1"}'])
def test_non_list_review_ids_become_empty(engine, review_ids):
    result, _ = ask(
        engine, f'{{"status": "answered", "answer": "Slow.", "review_ids": {review_ids}}}'
    )

    assert result["review_ids"] == []


def test_out_of_scope_reply_never_cites_reviews(engine):
    result, _ = ask(
        engine,
        '{"status": "out_of_scope", "answer": "I can only answer about these reviews.",'
        ' "review_ids": ["slow-1"]}',
        question="What is the weather today?",
    )

    assert result["status"] == "out_of_scope"
    assert result["review_ids"] == []


@pytest.mark.parametrize(
    "reply",
    [
        '{"status": "maybe", "answer": "Slow.", "review_ids": []}',
        '{"answer": "Slow.", "review_ids": []}',
        '{"status": "answered", "answer": "   ", "review_ids": []}',
        '{"status": "answered", "review_ids": ["slow-1"]}',
        '{"status": "answered", "answer": 42, "review_ids": []}',
    ],
)
def test_reply_with_bad_status_or_answer_maps_to_qa_unavailable(engine, reply):
    with pytest.raises(QaUnavailable):
        ask(engine, reply)


def test_bad_model_reply_returns_503_over_api(qa_client, auth_header):
    app = qa_client('{"status": "maybe", "answer": "Slow.", "review_ids": []}')
    response = app.test_client().post(
        "/api/targets/a/questions",
        json={"question": "What do customers complain about?"},
        headers=auth_header("user-a"),
    )

    assert response.status_code == 503
