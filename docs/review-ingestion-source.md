# ReviewLens Sprint 1 — Google Maps review acquisition

The application supports **one review platform: Google Maps**, with two acquisition methods.

1. **Live retrieval:** For full Google Maps place links containing a `data_id` or a `place_id`, configure the backend-only `SERPAPI_API_KEY` in `backend/.env`. The existing **Start ingestion** button makes a bodyless `POST /api/targets/{id}/ingestions`. The Flask service checks ownership and the saved URL before calling SerpApi's structured Google Maps Reviews API. Shortened `maps.app.goo.gl` links are not automatically resolved: use a full place link.
2. **Supplied data:** A signed-in user may import an authentic CSV export of Google Maps reviews using the `POST /api/targets/{id}/ingestions/import` multipart endpoint with a `file` field. This is an explicit *user-supplied import* and must never be represented as data independently fetched by the app. Required CSV headers are `review_text` and `rating` (aliases `text`/`review` and `stars` supported). Optional columns: `reviewer_name`, `review_date`, `source_review_id`, `review_url`.

The backend does not fabricate records. Each successful Review contains written text and a 1–5 rating. Invalid individual records are skipped; an import that contains some valid and some invalid records is marked `partial`. A completely unusable file is `failed`. Counts and latest run state come from persisted database records, not Gemini or hardcoded values. Prior valid reviews are not erased if another ingestion fails.

### Skipped and rejected records (S2-007)

Each skipped record is assigned exactly one user-facing reason category. Raw parser diagnostics are never exposed:

| Category | Meaning |
| --- | --- |
| `missing_text` | No written review text (blank or absent). |
| `text_too_long` | Review text longer than 20,000 characters. |
| `invalid_rating` | Rating missing, non-numeric, or outside 1–5. |
| `malformed_record` | The source record is not a usable object/row. |

Per-category counts are stored in `ingestion_run_skip_reasons` and returned on every run as `skip_reasons`, e.g. `{"missing_text": 2, "invalid_rating": 1}`. They always sum to `skipped_count`. A run where every record was rejected is `failed`, but it still keeps its `total_count`, `skipped_count`, and `skip_reasons`. The workspace shows the breakdown and states that skipped records are not included in the review dataset. Skipped records are never persisted, so they are never counted by the summary or used by Q&A.

## Security / deployment

- Only the verified Supabase JWT `sub` determines the owner. The backend checks ownership before external fetch or reading CSV contents. Authenticated non-owners receive 404, not target data.
- Only Flask sends the SerpApi key. Never use `VITE_SERPAPI_API_KEY` or put it in a browser payload.
- Do not log provider URLs (they contain `api_key`) or exception bodies from the provider. Provider errors are converted to safe user-facing messages.
- CSV file limit: 2 MB and 5,000 rows. API request maximum: 3 MB. Ingestion occurs synchronously for this Sprint 1 baseline.
- This Sprint 1 implementation does not deduplicate repeat ingestions. Use one import per target for the class demo.
- `flask --app app init-db` creates missing tables. It is **not** a production migration mechanism; do not use it to revise existing tables.
- After pulling S2-007, re-run `flask --app app init-db` once against each existing database. It adds the new `ingestion_run_skip_reasons` table (with RLS enabled); without that table, reading ingestion runs fails.
- Example fixture files in automated tests are synthetic **test fixtures**, not actual customer review evidence for a demo. Use genuine supplied reviews for the demo.

## Acceptance test order

1. Register or log in with User A; create a Google Maps analysis target.
2. Import a genuine CSV export using the Review CSV control, or add the private SerpApi key and use a full Google Maps place URL.
3. Confirm an ingestion run reports `succeeded` or `partial`; reload the workspace and confirm it retains the result.
4. Query `/api/targets/{id}/reviews` as User A and confirm stored text and ratings.
5. Log in as User B. Attempt to read or ingest User A's target directly by ID; both must return 404 with no data leaked.
6. Upload a malformed CSV as User A; confirm failed run state and unchanged valid reviews.
7. Run backend Ruff and pytest, frontend ESLint/Vitest/build, and ensure required PR checks are green before merge.

Official external API contract: https://serpapi.com/google-maps-reviews-api .
