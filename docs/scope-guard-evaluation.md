# S2-004 — Repeatable scope-guard evaluation

The evaluation set is `backend/tests/fixtures/scope_guard_cases.json`. Its synthetic Harbor Cafe review dataset intentionally covers coffee, service, and pastries **but not** parking, accessibility, or Wi-Fi. There are three questions in each required category: in-scope, insufficient evidence, general knowledge, another entity/product, and another platform.

## Automated, no-credit validation

From `backend/`: `python -m pytest tests/test_scope_guard_evaluation.py -q`

This validates the fixture, expected outcomes, and result-scoring contract. **It does not prove Gemini responds correctly**: the model is nondeterministic and is not called by CI. Do not count this as a live model score.

## Optional live evaluation (Gemini API credits)

With an approved backend-only `GEMINI_API_KEY` in `backend/.env`:

`python -m scripts.evaluate_scope_guard --live`

Optionally pass `--model MODEL` or `--limit 3`. The evaluation sends **only synthetic fixture data**, never data from the live Supabase database. It checks category (`answered`, `insufficient_evidence`, `out_of_scope`), nonempty explanatory text, and evidence citation integrity, not exact answer wording. The exit code is nonzero for mismatches. Run it after prompt changes, especially when S2-012/S2-014/S2-015 merge. Results vary with the model and current service configuration.

No calls to Supabase or writes to the project database occur in this evaluation. The fixture is a controlled behavioral test corpus, not fake production reviews.
