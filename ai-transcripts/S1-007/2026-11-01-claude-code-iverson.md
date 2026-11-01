# S1-007 Pull request CI: AI session transcript

- **Story:** S1-007 Pull request CI
- **Date:** 2026-11-01
- **Tool:** Claude Code
- **Author:** Iverson Lopez
- **Format:** Condensed transcript. Key messages, commands, and results are kept in order,
  including dead ends. Routine back and forth is shortened.

---

## 1. Kickoff and context

**Iverson:**
> Before doing anything, read everything in the claude-context/ folder ...
> specs/sprint1-rules-and-stories.md is the grading source of truth.
> Run git status and git log -5 ... Run the backend tests ... and the frontend checks ...
> My tickets are S1-005 to S1-008 ... S1-007 (PR CI), then S1-006, then S1-005, then S1-008.
> Before writing code for a ticket, show me a short plan and the files you'll touch.

**Claude:** Read the local context notes, the Sprint 1 stories, `docs/coding-standards.md`,
`docs/data-and-security-guardrails.md`, and `docs/ai-assisted-development.md`.

```bash
git status
git log -5 --oneline
```

```
On branch main, up to date with origin/main
0496c4e Merge pull request #29 from bdorf04NJIT/feature/authenticated-identity
```

**Claude:** Still at `0496c4e`. `backend/.venv` and `frontend/node_modules` were missing, so
tests could not run yet. Also checked toolchain versions:

```
python --version   -> Python 3.13.7
node --version     -> v20.20.0
```

Checked engine requirements in `frontend/package-lock.json`:

| Package | Needs Node |
|---|---|
| vite 8 | ^20.19.0 or >=22.12.0 |
| vitest 5 | ^22.12.0 or newer |
| jsdom 30 | ^22.22.2 or newer |

**Claude:** Node 20 would fail `npm test`. 

---

## 2. Understanding the setup

**Iverson:** asked for the setup findings explained one chunk at a time.

**Claude:** Explained three points:
1. The repo lists dependencies, but `.venv` and `node_modules` are local and never committed.
2. Node 20 is too old for Vitest 5 and jsdom 30.
3. Tests and build need no `.env` files. Tests inject fake config. Only running the app needs them.

**Iverson:**
> are we going in order of the tickets to do them or based on how the project is right now

**Claude:** Ticket numbers are labels, not a sequence. Order is by need: 007 first because
there is no CI and the demo opens with CI, then 006 since CI runs those tools, then 005 to
document the real commands, then 008 polish. Local setup comes before all of them.

---

## 3. Local setup

**Iverson:** "okay install the latest"

```powershell
nvm version        # 1.2.2, nvm for Windows already installed
nvm install 22     # Downloading node.js version 22.23.4 ... Installation complete
nvm use 22.23.4
node --version     # v22.23.4
```

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
```

Dead end: the frontend install was started in parallel with a relative `Set-Location frontend`
while the shell was already inside `backend/`, so it failed with "Cannot find path
...\backend\frontend". Reran with an absolute path:

```powershell
cd frontend
npm ci
```

Baseline checks on `main`:

```
backend:  python -m pytest      -> 28 passed in 1.44s
frontend: npm run lint          -> exit 0
frontend: npm test              -> Test Files 1 passed, Tests 9 passed
frontend: npm run build         -> built in 419ms
frontend: npm audit             -> 12 moderate severity vulnerabilities
```

**Claude:** All 12 audit findings are in the ESLint and typescript-eslint dev toolchain, not
in code shipped to the browser. Left alone for now. Dependency scanning is a Sprint 3 gate.
Correction to the earlier audit notes: backend has 28 test cases, not about 20.

---

## 4. Choosing the scope

**Claude:** The draft workflow in the notes runs `ruff`, but ruff is not installed yet. That
is S1-006. Two options:

- **A:** S1-007 ships CI with the checks that exist today. S1-006 adds ruff and Prettier and
  extends `ci.yml`. One ticket per branch, green from day one.
- **B:** add ruff to `requirements.txt` and a config inside S1-007. Complete in one shot, but
  mixes S1-006 work into this PR.

Recommended A.

**Iverson:** "Okay do A"

---

## 5. Team process check

**Iverson:** "wait where is our teams ai doc?"

**Claude:** `docs/ai-assisted-development.md` (S1-004). Rules that apply to this PR:
- The PR description must say it contains AI generated code.
- A teammate other than the author approves.
- CI workflow changes get a second reviewer, checked against the security doc.
- A transcript is committed under `ai-transcripts/<story-id>/` in the same PR.

```bash
git log --all --oneline -- ai-transcripts     # no output
gh pr list --state merged --limit 10 --json number,title,body,author
```

**Claude:** Confirmed. No transcripts exist, and PRs #24 to #29 have no Test Evidence
sections. Three have empty descriptions. Test Evidence is required by the Sprint 1
Definition of Done:

> The pull request contains a short Test Evidence section describing the tests used to
> verify the story.

The transcript rule is the team's own answer to S1-004 topic 6, "How AI session transcripts
are retained for the project." This PR follows both.

---

## 7. Plan (approved)

- Branch `feature/S1-007-pr-ci` off `main`.
- One new file: `.github/workflows/ci.yml`. Nothing else touched.
- Triggers: every `pull_request`, and push to `main`.
- `frontend` job: Node 22, `npm ci`, lint, unit tests, build.
- `backend` job: Python 3.12, install, syntax check as the build step, pytest.
- Read only workflow permissions. No secrets.

**Iverson:** "okay do 1-3"

---

## 8. Implementation

```bash
git checkout -b feature/S1-007-pr-ci
```

Created `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  frontend:      # checkout, setup-node 22 (npm cache), npm ci, lint, test, build
  backend:       # checkout, setup-python 3.12 (pip cache), pip install,
                 # python -m compileall -q app, pytest
```

Design notes:
- Python has no build step, so `python -m compileall -q app` stands in. It fails on any
  syntax error.
- Backend tests need no secrets. `tests/conftest.py` passes a fake `SUPABASE_URL`, an HS256
  test secret, and a temporary SQLite `DATABASE_URL` with `TESTING=True`.
- Frontend tests mock `./lib/supabase`, and the build does not read env values at compile time.
- Job names `frontend` and `backend` are the checks to require in branch protection.

---

## 9. Verification

Dead end: the first YAML parse attempt used a Node `yaml` package that is not installed.

```
Error: Cannot find module './frontend/node_modules/yaml'
```

Switched to PyYAML, installed in the local venv only. Not added to `requirements.txt`.

```
triggers: ['pull_request', 'push']
jobs: ['frontend', 'backend']
frontend -> Check out repository | Set up Node.js | Install dependencies | Lint | Unit tests | Build
backend  -> Check out repository | Set up Python | Install dependencies | Build (syntax check) | Unit tests
```

Ran every workflow command locally on the branch:

| Command | Result |
|---|---|
| `python -m compileall -q app` | exit 0 |
| `pytest` | 28 passed |
| `npm run lint` | exit 0 |
| `npm test` | 9 passed |
| `npm run build` | built, exit 0 |

```bash
git status --short
?? .github/workflows/ci.yml
```

---

## 10. Transcript

**Iverson:** asked for a short summary transcript, then asked to see the full export for
comparison, then settled on this condensed version.
