"""S2-015: decline questions about another business, product, or review platform.

Scope is enforced primarily by the system prompt (S2-BR-019), so these tests check three
things deterministically, without a live model:

1. The prompt states the rule, names the active target and platform, and carries the
   comparison exception.
2. Every evaluation question reaches the model unchanged with that prompt and the active
   reviews. There is no keyword blacklist in the app (S2-BR-020), and reviews that
   mention another business are not filtered out, because the comparison exception
   depends on them.
3. Controlled model decisions come back to the user correctly: a decline is returned as
   ``out_of_scope`` with no cited reviews, and the in-scope controls stay answered.

The questions live in tests/scope_eval/other_entity_or_platform.json so the S2-004
evaluation set can reuse them. ``test_live_model_follows_the_scope_rules`` replays the
same cases against real Gemini. It is skipped unless RUN_LIVE_SCOPE_EVAL=1 and
GEMINI_API_KEY are set, so CI never makes paid or nondeterministic calls.
"""

import json
import os
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import create_app
from app.models import AnalysisTarget, Base
from app.services.qa_prompt import (
    ANSWERED,
    OUT_OF_SCOPE,
    PROMPT_VERSION,
    RESPONSE_STATUSES,
    build_system_prompt,
)
from app.services.review_qa import answer_question
from app.services.review_storage import persist_reviews

SECRET = "test-secret-at-least-32-bytes-long!!"  # matches conftest.auth_header
EVAL = json.loads(
    (Path(__file__).parent / "scope_eval" / "other_entity_or_platform.json").read_text("utf-8")
)
TARGET = EVAL["target"]
CASES = EVAL["cases"]
CASE_IDS = [case["id"] for case in CASES]


class RecordingGemini:
    """Fake model boundary: records each call and replies with the next scripted reply."""

    def __init__(self):
        self.calls = []
        self.reply = None

    def answer(self, *, system_prompt, user_content):
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content})
        return self.reply


def seed_target(engine, *, target_id="t1", owner_id="user-a"):
    """Create the evaluation target and its reviews; return {review key: review id}."""
    with Session(engine) as session, session.begin():
        session.add(
            AnalysisTarget(
                id=target_id,
                owner_id=owner_id,
                name=TARGET["name"],
                platform=TARGET["platform"],
                source_url="https://www.google.com/maps/place/Joes+Coffee",
            )
        )
    persist_reviews(
        engine,
        owner_id=owner_id,
        target_id=target_id,
        source_kind="google_maps_csv",
        reviews=[{"text": r["text"], "rating": r["rating"]} for r in EVAL["reviews"]],
        skipped_count=0,
    )
    user_content = _capture_context(engine, target_id=target_id, owner_id=owner_id)
    by_text = dict(re.findall(r'<review id="([^"]+)"[^>]*>(.*?)</review>', user_content))
    text_to_id = {text: review_id for review_id, text in by_text.items()}
    return {r["key"]: text_to_id[r["text"]] for r in EVAL["reviews"]}


def _capture_context(engine, *, target_id, owner_id):
    probe = RecordingGemini()
    probe.reply = json.dumps({"status": ANSWERED, "answer": "probe", "review_ids": []})
    answer_question(
        engine, probe, owner_id=owner_id, target_id=target_id, payload={"question": "probe"}
    )
    return probe.calls[0]["user_content"]


def controlled_reply(case, ids):
    """The reply a well-behaved model would give for this case."""
    if case["expected_status"] == OUT_OF_SCOPE:
        answer = f"I can only answer questions about the Google Maps reviews of {TARGET['name']}."
        return {"status": OUT_OF_SCOPE, "answer": answer, "review_ids": []}
    cited = [ids[key] for key in case["expected_citations"]]
    return {"status": ANSWERED, "answer": "One reviewer mentions it.", "review_ids": cited}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    monkeypatch.setenv("SERPAPI_API_KEYS", "")
    app = create_app(
        {
            "TESTING": True,
            "JWT_SECRET": SECRET,
            "SUPABASE_URL": "https://test.supabase.co",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'scope.db'}",
        }
    )
    engine = app.extensions["database"]
    Base.metadata.create_all(engine)
    ids = seed_target(engine)
    gemini = RecordingGemini()
    app.extensions["gemini"] = gemini
    yield app.test_client(), gemini, ids
    engine.dispose()


# --- 1. The prompt ----------------------------------------------------------------------


@pytest.fixture
def prompt():
    return build_system_prompt(target_name=TARGET["name"], platform=TARGET["platform"])


@pytest.mark.parametrize(
    "text",
    [
        "Decline questions about any other business, product, or location",
        "platform other than Google Maps (for example Yelp, Tripadvisor,\n   or Amazon)",
        'even when the question names "Joe\'s Coffee"',
        'You only have\n   Google Maps reviews for "Joe\'s Coffee"',
        "can be answered only from what these reviewers\n     themselves say about it",
        "If no supplied review makes that comparison, decline.",
        "including whether reviewers\n     mention another business or platform",
        "do not describe the\n  other business or platform. review_ids must be empty.",
    ],
)
def test_prompt_states_the_other_entity_and_platform_rules(prompt, text):
    assert text in prompt


def test_prompt_version_was_bumped_for_the_new_wording():
    # S2-015 introduced version 4; later stories may bump it further.
    assert int(PROMPT_VERSION) >= 4


# --- 2. The evaluation set itself --------------------------------------------------------


def test_evaluation_set_covers_obvious_and_reasonable_phrasings():
    declined = [c for c in CASES if c["expected_status"] == OUT_OF_SCOPE]
    for category in ("other_entity", "other_platform"):
        phrasings = {c["phrasing"] for c in declined if c["category"] == category}
        assert phrasings == {"obvious", "reasonable"}, category
    # In-scope controls keep the guard from passing by refusing everything.
    assert any(c["expected_status"] == ANSWERED for c in CASES)
    assert len(set(CASE_IDS)) == len(CASE_IDS)
    for case in CASES:
        assert case["expected_status"] in RESPONSE_STATUSES
        assert case["question"].strip()


# --- 3. Orchestration with controlled model decisions ------------------------------------


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_question_reaches_the_model_with_the_scope_prompt_and_active_reviews(
    api, auth_header, case
):
    client, gemini, ids = api
    gemini.reply = json.dumps(controlled_reply(case, ids))

    response = client.post(
        "/api/targets/t1/questions", json={"question": case["question"]}, headers=auth_header()
    )

    assert response.status_code == 200
    # No app-side keyword filter: the decision is the model's, guided by the prompt.
    assert len(gemini.calls) == 1
    call = gemini.calls[0]
    assert "Decline questions about any other business" in call["system_prompt"]
    assert '"Joe\'s Coffee"' in call["system_prompt"]
    assert f"Question: {case['question']}" in call["user_content"]
    # Reviews that mention another business or platform are still supplied as evidence.
    for review in EVAL["reviews"]:
        assert review["text"] in call["user_content"]


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["expected_status"] == OUT_OF_SCOPE], ids=lambda c: c["id"]
)
def test_declined_question_is_returned_as_a_refusal_without_evidence(api, auth_header, case):
    client, gemini, ids = api
    gemini.reply = json.dumps(controlled_reply(case, ids))

    body = client.post(
        "/api/targets/t1/questions", json={"question": case["question"]}, headers=auth_header()
    ).get_json()

    assert body["status"] == OUT_OF_SCOPE
    assert body["answer"].strip()
    assert body["review_ids"] == []


def test_refusal_that_wrongly_cites_reviews_is_returned_without_them(api, auth_header):
    # Even if the model ignores "review_ids must be empty", a decline never shows review
    # evidence, so it can't look like the other business was analyzed (S2-BR-021).
    client, gemini, ids = api
    gemini.reply = json.dumps(
        {"status": OUT_OF_SCOPE, "answer": "I can't compare.", "review_ids": list(ids.values())}
    )

    body = client.post(
        "/api/targets/t1/questions",
        json={"question": "How does Joe's Coffee compare with Starbucks?"},
        headers=auth_header(),
    ).get_json()

    assert body["status"] == OUT_OF_SCOPE
    assert body["review_ids"] == []


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["expected_status"] == ANSWERED], ids=lambda c: c["id"]
)
def test_comparison_backed_by_the_reviews_is_still_answered(api, auth_header, case):
    client, gemini, ids = api
    gemini.reply = json.dumps(controlled_reply(case, ids))

    body = client.post(
        "/api/targets/t1/questions", json={"question": case["question"]}, headers=auth_header()
    ).get_json()

    assert body["status"] == ANSWERED
    assert body["review_ids"] == [ids[key] for key in case["expected_citations"]]


# --- 4. Optional live check against real Gemini ------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_SCOPE_EVAL") != "1" or not os.environ.get("GEMINI_API_KEY"),
    reason="Live model check: set RUN_LIVE_SCOPE_EVAL=1 and GEMINI_API_KEY to run.",
)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_live_model_follows_the_scope_rules(case):
    from app.adapters.gemini_source import GeminiReviewAnswerer

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    ids = seed_target(engine)
    model = os.environ.get("GEMINI_MODEL") or None
    gemini = GeminiReviewAnswerer(os.environ["GEMINI_API_KEY"], model=model)

    result = answer_question(
        engine, gemini, owner_id="user-a", target_id="t1", payload={"question": case["question"]}
    )

    assert result["status"] == case["expected_status"], result["answer"]
    for key in case.get("expected_citations", []):
        assert ids[key] in result["review_ids"], result
