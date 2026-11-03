# S1-013 Cross-user review and ingestion authorization: AI session transcript

- **Story:** S1-013 Enforce Cross-User Review and Ingestion Authorization
- **Rules:** S1-BR-007 through S1-BR-010, S1-BR-018
- **Date:** 2026-11-03
- **Tool:** Claude Code (Claude Opus 5.5, VS Code extension)
- **Author:** Connor Melton
- **Branch:** `feature/S1-013-review-ingestion-authorization` (from `main` at `35134fb`, after S1-012 merged)
- **Format:** Condensed transcript. Secrets are `[REDACTED]` (none appeared). The full raw
  session log is kept locally by the author.
- **Continues from:** `ai-transcripts/S1-012/2026-11-03-claude-code-connor.md`

---

## 1. Scoping

> Given what's on this branch, what must be done minimum for this ticket?

Claude read `services/ingestion.py` and `services/review_storage.py`. Ownership of the parent
`AnalysisTarget` is already checked before every review or ingestion operation:

| Ticket item | Existing check | Added in |
| --- | --- | --- |
| Retrieve User A's reviews | `list_reviews` → `_owned_target` | S1-022 (`3c87065`) |
| Submit ingestion on User A's target | `start_ingestion` → `_ensure_owner`, before the source is called | S1-019 (`00b96c5`) |
| Create reviews under User A's target | `import_supplied_reviews` → `_ensure_owner`, before the upload is read. `persist_reviews` and `record_failed_run` check again. | S1-022 / S1-023 (`8b96802`) |

Reviews have no owner column. Ownership is inherited through
`Review.target_id → AnalysisTarget.owner_id`, which the ticket allows.

> You are arguing this got done in other tickets already?

Partly. The **enforcement** shipped with S1-019, S1-022, and S1-023. The **proof** did not.
The existing HTTP test runs User B against a target with zero reviews, so a leaky endpoint
could still pass it. The checks were also spread across files written for other tickets.

**Decision:** no production code changes. Add one dedicated test file that seeds real User A
data first.

---

## 2. Change: `backend/tests/test_review_authorization.py` (new)

```bash
git checkout -b feature/S1-013-review-ingestion-authorization
```

**Setup:** the `target_a` fixture has User A create Target A and import two reviews through
the CSV endpoint. `snapshot()` captures every `Review` and `IngestionRun` row, so any write by
User B shows up as a diff. `RecordingSource` is a fake provider that records calls and
returns a planted "Injected by B" review.

| Test | Proves |
| --- | --- |
| `test_owner_can_read_own_reviews` | Happy path. |
| `test_user_b_cannot_retrieve_target_a_reviews` | **Item 1.** Returns 404, and no User A review text leaks. |
| `test_user_b_cannot_see_target_a_ingestion_state` | `latest_ingestion` is not exposed to User B. |
| `test_user_b_cannot_start_ingestion_on_target_a` | **Item 2.** Returns 404, the source is never called, and the DB is unchanged. |
| `test_user_b_cannot_import_reviews_into_target_a` | **Item 3.** Returns 404, the DB is unchanged, and User A's reviews are intact. |
| `test_user_b_bad_upload_does_not_record_failed_run_on_target_a` | A bad file from User B records no failed run on Target A. |
| `test_denied_and_missing_targets_look_the_same` | On all 3 endpoints, the response for Target A matches the response for a made-up id. |
| `test_forged_owner_param_does_not_unlock_reviews` (×5) | `?owner_id=user-a` and similar params are ignored. |
| `test_user_b_writes_only_to_own_target` | Isolation works both ways. |
| `test_import_checks_owner_before_reading_upload` | Service level: the upload callable is never invoked. |
| `test_ingestion_checks_owner_before_validating_body_or_calling_source` | Service level: User B gets `NotFound`, not a validation error, and the source is never called. |

The last two cover "validate ownership of the parent AnalysisTarget before performing
child-resource operations."

`SOURCE_URL` (`https://www.google.com/maps/place/Coffee+Shop`) was reused from the existing
tests. It only needs to pass `source_url_error`. It is never fetched, because ingestion uses
the fake source and CSV import ignores the URL. The project rules forbid live services in tests.

---

## 3. Verification

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_review_authorization.py   # 15 passed
.venv/bin/python -m pytest -q                                      # 221 passed
.venv/bin/ruff check . && .venv/bin/ruff format --check .          # clean
```

**Mutation check.** Claude removed the owner filter from each check and reran the file.
`app/` had no uncommitted changes, so `git checkout app` restored it safely. This avoided the
S1-012 mistake, where `git checkout` also wiped uncommitted code.

| Owner filter removed from | New tests failing |
| --- | --- |
| `targets.find_owned_target` (ingestion and import entry check) | 8 / 15 |
| `review_storage._owned_target` (review reads and writes) | 7 / 15 |
| Both | 13 / 15 (only the 2 owner-only tests still pass) |

Removing either check on its own fails some tests.

---

## 4. Notes for the PR

- AI-assisted (Claude Code). Test-only change. The enforcement came from S1-019, S1-022, and S1-023.
- It covers ownership (S1-BR-008), so it needs a second security reviewer.
