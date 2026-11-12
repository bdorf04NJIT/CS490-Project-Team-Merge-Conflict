"""S2-004: optional live scope-guard evaluation, independent of real customer records.

Run from backend/: python -m scripts.evaluate_scope_guard --live
This *spends Gemini tokens* and requires GEMINI_API_KEY in backend/.env.
The evaluator checks outcomes and citations, never an exact answer sentence.
It does not write to the database or send actual customers' reviews to a model.
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from app.services.qa_prompt import build_system_prompt
from app.services.review_qa import _parse_reply, _reviews_block

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "scope_guard_cases.json"


def load_cases(path=FIXTURE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assess(case, result, review_ids):
    """Compare semantic status and grounded evidence, without answer-string equality."""
    if result.get("status") != case["expected_status"]:
        return False, "Incorrect outcome category"
    if not isinstance(result.get("answer"), str) or not result["answer"].strip():
        return False, "Missing plain-language answer"
    cited = result.get("review_ids")
    if not isinstance(cited, list) or not all(isinstance(item, str) for item in cited):
        return False, "Invalid evidence ids"
    if not set(cited).issubset(set(review_ids)):
        return False, "Evidence references unsupplied reviews"
    if case["expected_status"] == "answered" and not cited:
        return False, "Supported answer lacks review evidence"
    if case["expected_status"] != "answered" and cited:
        return False, "Decline or insufficient evidence has citations"
    return True, "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="ReviewLens scope guard evaluation")
    parser.add_argument("--live", action="store_true", help="Explicitly allow Gemini API calls")
    parser.add_argument("--model", help="Optionally pin a Gemini model")
    parser.add_argument("--limit", type=int, default=0, help="Limit the number of cases (0 = all)")
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("Refusing provider calls without --live. See docs/scope-guard-evaluation.md")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        parser.error("Set GEMINI_API_KEY in backend/.env (never commit or paste it)")
    from app.adapters.gemini_source import GeminiReviewAnswerer

    data = load_cases()
    reviews = [SimpleNamespace(**row) for row in data["reviews"]]
    block, sent_ids = _reviews_block(reviews)
    target = data["target"]
    system_prompt = build_system_prompt(target_name=target["name"], platform=target["platform"])
    provider = GeminiReviewAnswerer(key, model=args.model)
    cases = data["cases"][: args.limit or None]
    counts = Counter()
    failures = []
    for case in cases:
        try:
            raw = provider.answer(
                system_prompt=system_prompt,
                user_content=f"Question: {case['question']}\n\n{block}",
            )
            result = _parse_reply(raw, sent_ids)
            passed, reason = assess(case, result, sent_ids)
            reported = result["status"]
        except Exception:
            passed, reason, reported = False, "Provider/format error", "error"
        counts[case["category"]] += 1
        print(f"{'PASS' if passed else 'FAIL'} {case['id']} ({case['category']}): {reported}")
        if not passed:
            failures.append((case["id"], reason))
    print(f"Result: {len(cases) - len(failures)}/{len(cases)} passed")
    for case_id, reason in failures:
        print(f"  {case_id}: {reason}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
