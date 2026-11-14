"""S2-004: deterministic checks of the evaluation matrix and outcome scoring.

These tests do not claim a live Gemini model passes the evaluation. The opt-in live
runner is the separate evidence of model behavior; CI verifies repeatability.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from app.services.qa_prompt import RESPONSE_STATUSES, build_system_prompt
from scripts.evaluate_scope_guard import assess, load_cases

FIXTURE = Path(__file__).parent / "fixtures" / "scope_guard_cases.json"
CATEGORIES = {
    "in_scope",
    "insufficient_evidence",
    "general_knowledge",
    "other_entity",
    "other_platform",
}


def test_evaluation_has_multiple_distinct_cases_in_each_required_category():
    dataset = load_cases(FIXTURE)
    cases = dataset["cases"]
    counts = Counter(item["category"] for item in cases)
    assert CATEGORIES <= set(counts)
    assert all(counts[category] >= 3 for category in CATEGORIES)
    assert len({item["id"] for item in cases}) == len(cases)
    assert len({item["question"] for item in cases}) == len(cases)
    assert all(case["expected_status"] in RESPONSE_STATUSES for case in cases)
    assert set(dataset["target"]) == {"name", "platform"}
    assert all(1 <= review["rating"] <= 5 and review["text"] for review in dataset["reviews"])
    assert len({r["id"] for r in dataset["reviews"]}) == len(dataset["reviews"])


def test_expected_categories_follow_reviewlens_contract():
    cases = load_cases(FIXTURE)["cases"]
    assert all(
        case["expected_status"]
        == (
            "answered"
            if case["category"] == "in_scope"
            else "insufficient_evidence"
            if case["category"] == "insufficient_evidence"
            else "out_of_scope"
        )
        for case in cases
    )


def test_system_prompt_covers_all_scope_guard_behaviors():
    target = load_cases(FIXTURE)["target"]
    prompt = build_system_prompt(target_name=target["name"], platform=target["platform"])
    for meaning in (
        "supplied reviews",
        "outside knowledge",
        "enough",
        "other business",
        "platform",
    ):
        assert meaning.lower() in prompt.lower()


def test_evaluation_accepts_paraphrases_not_exact_answer_text():
    case = next(case for case in load_cases(FIXTURE)["cases"] if case["category"] == "in_scope")
    assert assess(
        case,
        {"status": "answered", "answer": "One reviewer loved it.", "review_ids": ["coffee-1"]},
        ["coffee-1"],
    )[0]
    assert assess(
        case,
        {"status": "answered", "answer": "Coffee receives praise.", "review_ids": ["coffee-1"]},
        ["coffee-1"],
    )[0]


@pytest.mark.parametrize(
    ("status", "ids", "expected"),
    [
        ("out_of_scope", [], True),
        ("answered", ["coffee-1"], False),
        ("out_of_scope", ["coffee-1"], False),
        ("invalid", [], False),
    ],
)
def test_evaluation_checks_outcome_and_citation_integrity(status, ids, expected):
    case = next(case for case in load_cases(FIXTURE)["cases"] if case["category"] == "other_entity")
    ok, _ = assess(
        case, {"status": status, "answer": "A reasonable reply.", "review_ids": ids}, ["coffee-1"]
    )
    assert ok is expected


def test_fixture_is_plain_json_without_provider_keys():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "api_key" not in json.dumps(data).lower()
    assert "gemini" not in json.dumps(data["reviews"]).lower()
