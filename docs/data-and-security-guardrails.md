# ReviewLens Data and Security Guardrails

**Users may access only their own data.** Every backend read and write must enforce this rule. This is called tenant isolation.

## Sign-in and user identity

ReviewLens uses **Supabase Auth** for registration, login, logout, and password reset.

The Python backend (Flask or FastAPI) must verify each access token's signature, expiration, issuer, and audience. Reject requests with missing or invalid authentication without returning protected data.

The verified token's `sub` field is the user's Supabase ID. Use it to identify the application User. If the application stores its own User records, each must map uniquely to a Supabase user.

When creating a target, the backend assigns its owner from this verified identity. Ordinary updates must not change ownership.

## Who owns the data?

- **AnalysisTarget:** belongs to one User.
- **IngestionRun:** belongs to a target and inherits its owner.
- **Review:** belongs to a target and inherits its owner. If linked to an ingestion run, both must belong to the same target.
- **Summaries and Q&A:** use only data from the target the user is allowed to access.

## Where access is checked

The backend must check ownership for every read and write, including lists, targets, reviews, ingestion runs, summaries, and Q&A.

- Filter database queries by the verified user, directly or through the target's owner.
- Before accessing a review or run, check that it belongs to a target the user owns.
- Check access before changing data, processing ingestion, or calling external services.
- If access is denied, return no protected data and make no changes.

## What must never be trusted

Users can change IDs sent in URLs or request bodies. An ID tells the backend which record is requested; it does not prove ownership.

- Reject ownership fields such as `userId` or `ownerId` supplied by the client. Use the verified token instead.
- Never read or change a record by ID without checking ownership.
- Never fetch other users' data and rely on the browser to filter it out.
- Never rely on hidden buttons or frontend route guards to protect backend data.

## Secrets and configuration

Store secrets according to where the application runs:

- **Local development:** ignored environment files.
- **Deployment:** the hosting platform's environment settings.
- **CI:** GitHub Actions secrets.

List required configuration names with placeholder values in `.env.example`. Missing required configuration must produce a clear error without revealing secret values.

Keep database credentials, Supabase secret/service-role keys, ingestion keys, and Gemini keys on the backend. Only configuration the provider designates as public may reach the frontend. Never put private credentials in Vite's `VITE_*` variables.

Do not commit secrets or include credentials or tokens in logs or error messages.

## How to test isolation

Use pytest with two signed-in users, User A and User B, each with their own targets, runs, and reviews. Test backend requests directly, using isolated test data and mocked external services.

Verify that:

1. Users can access their own data. Requests without authentication fail and return no protected data.
2. Each user's target list contains only their own targets.
3. User B cannot read, update, or delete User A's targets, reviews, or runs, even when B knows their IDs.
4. User B cannot start ingestion or create reviews or runs under User A's target. Denied requests make no changes or external calls.
5. Forged ownership fields and IDs for reviews or runs from a different target cannot bypass access checks.
6. Summaries and Q&A never include another user's data.
7. After denying cross-user requests, the same operations still succeed for the rightful owner.
