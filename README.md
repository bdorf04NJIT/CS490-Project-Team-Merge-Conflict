# ReviewLens AI

ReviewLens is a multi-user web app for review analysis. An analyst creates a target (a
product or business), ingests its public reviews from a URL, and asks questions answered
only from those reviews. Each user can see only their own targets and reviews.

CS 490 capstone, team Merge Conflict.

## Repo layout

| Folder | What's in it |
|---|---|
| `frontend/` | React + Vite + TypeScript + Tailwind app. See [frontend/README.md](frontend/README.md) |
| `backend/` | Flask API with SQLAlchemy and Supabase Postgres. See [backend/README.md](backend/README.md) |
| `docs/` | Team standards and the local setup guide |
| `ai-transcripts/` | AI development transcripts, one folder per story |
| `.github/workflows/` | CI (`ci.yml`) and the sprint issue importer |

Storage config lives in `backend/.env` (`DATABASE_URL`) and is read by
`backend/app/database.py`. The frontend calls the backend through the Vite proxy (`/api`
goes to `http://127.0.0.1:5000`), so no API URL is hard coded.

## Prerequisites

- Python 3.12 or newer
- Node.js 22 LTS (22.22 or newer) and npm
- Access to the team's Supabase project, as well as dev values.

## Quick start

1. Set up env files. Copy `backend/.env.example` to `backend/.env` and
   `frontend/.env.example` to `frontend/.env.local`, then fill in the values shared
   privately by the team. Never commit these files.
2. Start the backend in one terminal. Follow [backend/README.md](backend/README.md).
3. Start the frontend in a second terminal. Follow [frontend/README.md](frontend/README.md).
4. Open the URL Vite prints (usually http://localhost:5173) and sign in.

New to the project? The [local setup guide](docs/local-env-setup-guide.md) walks through
every step, including Mac and Linux commands and common errors.

## Checks

Run these before pushing. CI runs the same commands on every pull request.

| Task | Frontend (in `frontend/`) | Backend (in `backend/`, venv active) |
|---|---|---|
| Lint | `npm run lint` | `ruff check .` |
| Format (fix) | `npm run format` | `ruff format .` |
| Format (check only) | `npm run format:check` | `ruff format --check .` |
| Unit tests | `npm test` | `pytest` |
| Build | `npm run build` | `python -m compileall -q app` |

Tests and builds need no env files or secrets. Backend tests use fake config and a temporary
SQLite database. Frontend tests mock the Supabase client.

## CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs two jobs on every pull request and
on every push to `main`:

- `frontend`: install, lint, format check, unit tests, build
- `backend`: install, lint, format check, build (syntax check), unit tests

If a PR fails on **Format check**, run the format command for that side and push again.

## Team docs

- [Coding standards](docs/coding-standards.md)
- [Data and security guardrails](docs/data-and-security-guardrails.md)
- [AI-assisted development and review](docs/ai-assisted-development.md)
- [Local setup guide](docs/local-env-setup-guide.md)
