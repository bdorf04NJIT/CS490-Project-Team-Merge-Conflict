# S1-005 Project structure and local dev workflow: AI session transcript

- **Story:** S1-005 Establish Project Structure and Local Development Workflow
- **Date:** 2026-11-01
- **Tool:** Claude Code
- **Author:** Iverson Lopez
- **Format:** Condensed transcript. Key messages, commands, and results are kept in order,
  including dead ends. Routine back and forth is shortened. Secrets are `[REDACTED]`.
  The full raw session log is kept locally by the author.
- **Continues from:** `ai-transcripts/S1-006/2026-11-01-claude-code-iverson.md`

---

## 1. Starting point

S1-006 (PR #35) was merged and CI passed on `main`.

**Iverson:** asked whether the repo should have somewhere that records the lint and format
fix commands, so teammates and their AI tools can find them.

**Claude:** That is part of S1-005. The root README gets a commands table. Also noted that
Claude Code automatically loads a root `CLAUDE.md` but not `README.md`.

**Iverson:** asked whether `CLAUDE.md` is mentioned in any team or professor doc.

```bash
grep -rn -i "CLAUDE.md|AGENTS.md|context file|AI tools" --include=*.md --include=*.csv .
```

**Claude:** Not mentioned anywhere. Stories S1-001 to S1-004 call the docs "context
documents" for developers and AI tools, and `docs/ai-assisted-development.md` says to give
AI tools those docs manually. A `CLAUDE.md` would be optional.

**Iverson:** decided to skip `CLAUDE.md`. Also skipped adding `.gitattributes` for line
endings.

---

## 2. Current state

```bash
git log --format='%h %an %ad %s' --date=short -- docs/local-env-setup-guide.md README.md
wc -c docs/local-env-setup-guide.md README.md
```

```
f2cec4b Connor Melton 2026-10-28 S1-010: minimal Flask skeleton with JWT auth
daa0e31 Brett Dorfman 2026-10-20 first commit
 0 docs/local-env-setup-guide.md
76 README.md
```

- Root `README.md`: title only, saved as UTF-16, which GitHub renders as spaced out characters.
- `docs/local-env-setup-guide.md`: empty, nothing links to it.
- `backend/README.md` and `frontend/README.md`: accurate, but the frontend one says Node
  22.12+. jsdom 30 needs 22.22.2+, found during S1-007 setup.

---

## 3. Plan (approved)

Branch `feature/S1-005-readme`.

1. Rewrite `README.md` as UTF-8: what ReviewLens is, repo layout, prerequisites, quick start,
   commands table, CI summary, links to team docs.
2. Fill `docs/local-env-setup-guide.md`: clone to running app, env files, Mac and Linux
   commands, troubleshooting for errors actually hit this session.
3. `frontend/README.md`: fix the Node version line.
4. Transcript.

No real values anywhere. Migrations stay a team decision; the guide documents
`flask init-db` as it works today.

**Iverson:** "okay do that"

---

## 4. Implementation

```bash
git checkout -b feature/S1-005-readme
gh issue list --state all --search "S1-005 in:title"    # #5
```

### `README.md`

Deleted and recreated so the file is UTF-8 instead of UTF-16.

```
file README.md   -> ASCII text
wc -l README.md  -> 71
```

Sections: intro, repo layout table, where storage config lives (`DATABASE_URL` in
`backend/.env`, read by `backend/app/database.py`), the Vite `/api` proxy, prerequisites,
quick start, checks table, CI jobs, team doc links.

Checks table:

| Task | Frontend | Backend |
|---|---|---|
| Lint | `npm run lint` | `ruff check .` |
| Format (fix) | `npm run format` | `ruff format .` |
| Format (check only) | `npm run format:check` | `ruff format --check .` |
| Unit tests | `npm test` | `pytest` |
| Build | `npm run build` | `python -m compileall -q app` |

### `docs/local-env-setup-guide.md`

Nine steps: install tools, clone, backend setup, frontend setup, env files, `init-db`, run
the app, run the checks, troubleshooting.

Troubleshooting rows come from real errors in the code and in this session:

- Node older than 22.22 (hit during S1-007 setup)
- `Set SUPABASE_URL in backend/.env` (`backend/app/__init__.py`)
- `Set DATABASE_URL ...` and `DATABASE_URL must use postgresql+psycopg://`
  (`backend/app/database.py`)
- `Set Supabase configuration in frontend/.env.local` (`frontend/src/lib/supabase.ts`)
- Vite proxy error when the backend isn't running
- Missing ruff or Prettier after pulling S1-006
- CI failing on Format check
- Lockfile churn from npm 10 (hit during S1-006)

The guide also warns that anything prefixed `VITE_` is bundled into browser code, so only
the Supabase publishable key belongs in the frontend.

### `frontend/README.md`

```
- Requires Node.js 22.12+ and npm.
+ Requires Node.js 22 LTS (22.22 or newer) and npm.
```

---

## 5. Verification

```bash
cd frontend
npm run format:check
npx prettier --check README.md ../README.md ../docs/local-env-setup-guide.md
```

```
All matched files use Prettier code style!          # frontend/, what CI checks
[warn] ../README.md                                  # root docs, not checked by CI
[warn] ../docs/local-env-setup-guide.md
```

Prettier would only re-pad markdown tables in the two root docs. CI's format check covers
`frontend/` only, so they were left as written.

Every relative link in the new docs was checked to point at a real file: 10 of 10 resolve.

Secret scan on all three files: 0 matches.

No code changed, so lint, tests, and build are unaffected.

---

## 6. Not done in this session

- Commit, push, and open the PR. Waiting on the author's review.
- Migrations decision (Alembic vs `flask init-db`) is still open for the team.
