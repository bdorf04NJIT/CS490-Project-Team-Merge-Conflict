# Local Environment Setup Guide

This guide takes a new developer from a fresh clone to a running app with passing checks.
Commands are shown for Windows PowerShell first, with Mac and Linux versions where they differ.

## 1. Install the tools

| Tool | Version | Check with |
|---|---|---|
| Git | any recent | `git --version` |
| Python | 3.12 or newer | `python --version` (Mac/Linux: `python3 --version`) |
| Node.js | 22 LTS, 22.22 or newer | `node --version` |
| npm | comes with Node. npm 11 recommended | `npm --version` |

Node 20 is too old. Vitest and jsdom refuse to run on it, so `npm test` fails. If you use
nvm, run `nvm install 22` and `nvm use 22`. To match the lockfile format the team uses,
upgrade npm with `npm install -g npm@11`.

## 2. Clone the repo

```powershell
git clone https://github.com/bdorf04NJIT/CS490-Project-Team-Merge-Conflict.git
cd CS490-Project-Team-Merge-Conflict
```

## 3. Backend setup

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Mac/Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.venv/` is local to your machine and ignored by git.

## 4. Frontend setup

```powershell
cd frontend
npm ci
```

Use `npm ci`, not `npm install`. It installs the exact versions in `package-lock.json` and
never rewrites the lockfile.

## 5. Environment files

Each developer creates their own env files. They are ignored by git and must never be
committed. Get the real values from a teammate privately, not in a commit, issue, or PR.

| Copy this | To this | Values |
|---|---|---|
| `backend/.env.example` | `backend/.env` | `SUPABASE_URL`, `DATABASE_URL` |
| `frontend/.env.example` | `frontend/.env.local` | `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` |

Windows PowerShell, from the repo root:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Mac/Linux:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Notes on the values:

- `DATABASE_URL` must start with `postgresql+psycopg://` and end with `?sslmode=require`.
- `SUPABASE_URL` and `VITE_SUPABASE_URL` are the same project URL.
- Only the Supabase **publishable** key goes in the frontend. Anything starting with
  `VITE_` is bundled into browser code, so never put a database password or private key in
  a `VITE_` variable.

You only need env files to run the app. Lint, tests, and builds work without them.

## 6. Create the database tables

Run once, and again after a teammate adds a new table:

```powershell
cd backend
.\.venv\Scripts\python.exe -m flask --app app init-db
```

Mac/Linux, with the venv active: `flask --app app init-db`

This creates missing tables only. It does not change or drop existing tables.

## 7. Run the app

Use two terminals.

Terminal 1, backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m flask --app app run --debug
```

Mac/Linux, with the venv active: `flask --app app run --debug`

Terminal 2, frontend:

```powershell
cd frontend
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). Vite forwards `/api` requests to
the backend at http://127.0.0.1:5000, so keep both terminals running.

## 8. Run the checks

Run these before pushing. CI runs the same ones on every pull request.

Frontend, in `frontend/`:

```powershell
npm run lint
npm run format:check
npm test
npm run build
```

Backend, in `backend/`:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

Mac/Linux, with the venv active: `ruff check .`, `ruff format --check .`, `pytest`

To fix formatting automatically: `npm run format` in `frontend/`, or `ruff format .` in
`backend/`.

## 9. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `npm test` fails or npm warns `EBADENGINE` | Node is older than 22.22 | Install Node 22 LTS and reinstall with `npm ci` |
| `RuntimeError: Set SUPABASE_URL in backend/.env` | Missing backend env file or value | Create `backend/.env` (step 5) |
| `RuntimeError: Set DATABASE_URL in backend/.env ...` | `DATABASE_URL` empty | Add the connection string (step 5) |
| `DATABASE_URL must use postgresql+psycopg://` | Wrong URL prefix | Change the start of the URL to `postgresql+psycopg://` |
| Browser shows `Set Supabase configuration in frontend/.env.local` | Missing frontend env file | Create `frontend/.env.local` (step 5) |
| Vite logs `http proxy error` for `/api` | Backend isn't running | Start the backend (step 7) |
| `No module named ruff` or `prettier: not found` | Tools added after your last install | `pip install -r requirements.txt` in `backend/`, `npm ci` in `frontend/` |
| CI fails on **Format check** | Code isn't formatted | Run the format command (step 8) and push again |
| `package-lock.json` changes a lot after installing a package | Older npm rewrote it | `npm install -g npm@11`, restore the lockfile, reinstall |
