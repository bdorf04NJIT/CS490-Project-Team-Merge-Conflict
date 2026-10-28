# ReviewLens Engineering Context
Stack: React (Vite) + Tailwind, Flask, Supabase Postgres (SQLAlchemy), Supabase Auth, Gemini.

## 1. Repository Layout
**NOTE: Routes (controllers) call services. Services call adapters and models.**
```
/backend/app/{routes,services,adapters}, models.py, auth.py, errors.py
/backend/{migrations,tests}
/frontend/src/{pages,components,api,hooks}
/ai-transcripts
```

## 2. Naming
**NOTE: Use the language's standard convention for compatability with linters**
- Python: `snake_case` functions and files, `PascalCase` classes.
- React: `PascalCase` components, `camelCase` variables, `useX` hooks.
- DB: plural `snake_case` tables, `target_id` style foreign keys.
- API: lowercase plural paths (`/api/targets`).

## 3. Formatting and Linting
- Backend: `ruff`. Frontend: ESLint + Prettier.
- Both run in CI

## 4. Error Handling
- Define and use error types in `errors.py`
- Never return stack traces or DB errors

## 5. API Responses
- Error shape: `{"error": {"code", "message", "fields"}}`
- Codes: 400/422 validation, 401 unauthenticated, 403/404 forbidden/not found, 422 ingestion failed, 503 LLM unavailable, 500 internal.
- User id comes only from JWT Token (NOT passed in)

## 6. Logging
- Python `logging` with request id and target id.
- Never log secrets or tokens.

## 7. Dependencies
- Must pass `pip-audit` / `npm audit` in CI
- New external services go behind an adapter (Spec 2.3, 7.4)

## 8. Testing
- `pytest` (backend), Vitest (frontend).
- Each change needs a happy-path and a negative test.
- Required: auth, ownership, CSV validation, summary math.
- Q&A tests use the mock LLM client. Assert context and prompt.
