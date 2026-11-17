# ReviewLens AI

ReviewLens is a multi-user web app for review analysis. An analyst creates a target (a
business on Google Maps), brings in its reviews, and asks questions answered only from those
reviews. Reviews come from Google Maps through SerpApi, or from a CSV the user uploads. Each
user can see only their own targets and reviews.

CS 490 capstone, team Merge Conflict.

## Repo layout

| Folder               | What's in it                                                                                |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `frontend/`          | React + Vite + TypeScript + Tailwind app. See [frontend/README.md](frontend/README.md)      |
| `backend/`           | Flask API with SQLAlchemy and Supabase Postgres. See [backend/README.md](backend/README.md) |
| `docs/`              | Team standards and the local setup guide                                                    |
| `ai-transcripts/`    | AI development transcripts, one folder per story                                            |
| `.github/workflows/` | CI (`ci.yml`) and the sprint issue importer                                                 |

Storage config lives in `backend/.env` (`DATABASE_URL`) and is read by
`backend/app/database.py`. The frontend calls the backend through the Vite proxy (`/api`
goes to `http://127.0.0.1:5000`), so no API URL is hard coded.

## Prerequisites

- Python 3.12 or newer
- Node.js 22 LTS (22.22 or newer) and npm
- Access to the team's Supabase project, as well as dev values.
- Optional: a SerpApi key, for pulling reviews straight from Google Maps. Get one at
  https://serpapi.com/manage-api-key. CSV upload works without it.
- A Google Gemini API key, for asking questions about the reviews. Get one at
  https://aistudio.google.com/apikey. The app runs without it, but asking a question returns
  an error.

## Quick start

1. Set up env files. Copy `backend/.env.example` to `backend/.env` and
   `frontend/.env.example` to `frontend/.env.local`, then fill in the values shared
   privately by the team. Add your Gemini key as `GEMINI_API_KEY` in `backend/.env`, and
   your SerpApi key as `SERPAPI_API_KEY` if you have one. Never commit these files.
2. Start the backend in one terminal. Follow [backend/README.md](backend/README.md).
3. Start the frontend in a second terminal. Follow [frontend/README.md](frontend/README.md).
4. Open the URL Vite prints (usually http://localhost:5173) and sign in.

New to the project? The [local setup guide](docs/local-env-setup-guide.md) walks through
every step, including Mac and Linux commands and common errors.

## Using the app

1. Sign up or sign in.
2. Create a target with a name and its Google Maps link. Copy the full link from the
   address bar after opening the place, not the short `maps.app.goo.gl` link from Share.
3. Open the target's workspace and add reviews:
   - **Start ingestion** pulls reviews from Google Maps. Needs `SERPAPI_API_KEY`.
   - **Import CSV reviews** uploads your own export. Needs `review_text` and `rating`
     columns.
4. The workspace shows the saved result of the last ingestion: succeeded (green), partially
   succeeded with some records skipped (amber), or failed with the reason (red). It includes
   how many new reviews were added and when the run finished, and it reloads after every
   attempt, including failed ones. When records are skipped, it shows how many and why (for
   example "2 missing review text, 1 missing or invalid rating") and states that they are not
   part of the review dataset.
5. Once reviews are saved, the workspace shows a review summary: how many reviews were
   ingested, the average rating, and how many reviews have each star rating.
6. Ask a question about the reviews under **Ask about these reviews**, like "What do
   customers complain about most?" ReviewLens answers only from this target's saved reviews
   and shows how many of them mention the answer (for example "3 of 15 reviews mention
   this").
   - If the reviews don't talk about it (say, parking at night), the answer is labeled
     **Not covered by these reviews** instead of a guess.
   - If the question has nothing to do with the reviews (the weather, coding help, another
     business, or Yelp and other review sites), it's labeled **Outside the scope of these
     reviews** and declined.
   - If the target has no saved reviews yet, or its last ingestion failed, the question box
     is hidden and the workspace says to finish ingestion or import a CSV first.
7. Use **Switch target** to move to another one of your targets. The heading, summary, and
   Q&A all change to the new target, and the next question only uses its reviews.

The summary comes from the backend at `GET /api/targets/<id>/summary`, which calculates it
from the saved reviews. It returns the review count, the average rating, how many reviews have
each star rating, and the latest ingestion result. Reviews skipped during import are not
counted. Like every other endpoint, it only returns targets owned by the signed-in user. Q&A
reads the same saved reviews, so the summary and answers describe the same reviews.

Questions go to `POST /api/targets/<id>/questions`. The backend loads that target's reviews for the
signed-in user, adds them to a system prompt that limits Gemini to those reviews, and sends
the question. It sends at most the newest 200 reviews (about 120,000 characters) to stay
inside the model's limits. The prompt lives in source control in
`backend/app/services/qa_prompt.py`. Details on both review sources are in
[review ingestion](docs/review-ingestion-source.md).

## Checks

Run these before pushing. CI runs the same commands on every pull request.

| Task                | Frontend (in `frontend/`) | Backend (in `backend/`, venv active) |
| ------------------- | ------------------------- | ------------------------------------ |
| Lint                | `npm run lint`            | `ruff check .`                       |
| Format (fix)        | `npm run format`          | `ruff format .`                      |
| Format (check only) | `npm run format:check`    | `ruff format --check .`              |
| Unit tests          | `npm test`                | `pytest`                             |
| Build               | `npm run build`           | `python -m compileall -q app`        |

Tests and builds need no env files or secrets. Backend tests use fake config and a temporary
SQLite database. Frontend tests mock the Supabase client. Q&A tests use a fake Gemini model, so
they never call the real API or cost anything.

To check the scope guard against real Gemini, run the opt-in live evaluation. It uses API
credits, so it's not part of CI. See [scope-guard evaluation](docs/scope-guard-evaluation.md).

## CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs two jobs on every pull request and
on every push to `main`:

- `frontend`: install, lint, format check, unit tests, build
- `backend`: install, lint, format check, build (syntax check), unit tests

On pull requests, both jobs also run a changed-code coverage gate. See
[coverage gate](docs/coverage-gate.md).

If a PR fails on **Format check**, run the format command for that side and push again.

## Team docs

- [Coding standards](docs/coding-standards.md)
- [UI/UX context and conventions](docs/ui-ux-context.md)
- [Data and security guardrails](docs/data-and-security-guardrails.md)
- [AI-assisted development and review](docs/ai-assisted-development.md)
- [Local setup guide](docs/local-env-setup-guide.md)
- [Review ingestion](docs/review-ingestion-source.md)
- [SerpApi key management](docs/serpapi-key-management.md)
- [Changed-code coverage gate](docs/coverage-gate.md)
- [Scope-guard evaluation](docs/scope-guard-evaluation.md)
