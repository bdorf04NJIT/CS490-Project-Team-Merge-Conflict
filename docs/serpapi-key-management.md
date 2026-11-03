# SerpAPI key management and bounded backfill

ReviewLens supports **one or more explicitly team-authorized SerpAPI credentials**. Confirm permission to pool keys belonging to separate accounts under the provider's terms; do not create extra free accounts to evade plan limits. All credentials remain server-side.

## Configuration

Set **one** of the following in the ignored `backend/.env`, never in frontend code or a GitHub PR:

```dotenv
# Existing single-key configuration remains supported
SERPAPI_API_KEY=YOUR_REPLACEMENT_KEY

# Or: team-authorized comma-separated credentials (takes precedence)
SERPAPI_API_KEYS=TEAM_KEY_1,TEAM_KEY_2,TEAM_KEY_3
SERPAPI_MAX_PAGES=3
```

`SERPAPI_MAX_PAGES` accepts 1 through 10. Each page can use one search credit; stop at the configured maximum even if SerpAPI returns another pagination token. A result may contain only reviews from a subset of pages if the search ends early. No demo-ready claims should be made until a genuine live request and Supabase persistence are verified.

## Selection and failure behavior

- Searches rotate among eligible keys. A pool of 5–6 keys is permitted **only if each credential is authorized and pooling complies with SerpAPI's account terms**.
- SerpAPI's free Account API is checked (with a 60-second cache) before live requests; it reports monthly searches remaining and hourly throughput. Quota-exhausted credentials are paused until their next renewal, or rechecked after 24 hours if unknown. Hourly-limited credentials pause for one hour.
- On HTTP 429, the Account API is refreshed to distinguish monthly depletion from hourly throughput; only eligible keys are considered for the same request.
- An invalid or forbidden key (401/403) is quarantined until server restart/configuration; a malformed search (400), source error, or unexpected provider failure is *not* retried across all credentials.
- When all authorized credentials are unavailable, ingestion returns a safe 503 with no fabricated reviews. It does not silently fall back to sample data.
- Credential availability is tracked *in process only*. Render deployments with multiple worker processes or replicas need centralized quota state (or a single ingestion worker) before production use.
- The adapter does not log keys, account API responses, full request URLs, or provider exception strings.

## Live demo checklist

1. Rotate any previously shared keys and configure a replacement only in `.env`/hosting secrets.
2. Ensure the four Sprint 1 PRs are approved/merged and CI is green; implement this change on its own new branch/PR and obtain review.
3. Set a conservative `SERPAPI_MAX_PAGES=1` for the first live test; choose one *full* Google Maps place URL with a recognized place identifier. Start ingestion and inspect persisted count and status.
4. Increase to `3` for a small backfill only after checking available SerpAPI credits. The Account API can report remaining credits without spending a search.
5. Import once per target for the demo: **S1 does not deduplicate repeated imports**, so repeating an ingestion can create duplicate reviews. Implement unique `(target_id, source_review_id)` handling before repeated scheduled backfills.
6. Run the complete backend and frontend suites and two-account ownership tests. Keep failed runs and errors visible to the user.

Official docs: https://serpapi.com/account-api and https://serpapi.com/api-status-and-error-codes and https://serpapi.com/google-maps-reviews-api.
