# S1-006 Code quality and test tooling: AI session transcript

- **Story:** S1-006 Code quality and automated test tooling
- **Date:** 2026-11-01
- **Tool:** Claude Code
- **Author:** Iverson Lopez
- **Format:** Condensed transcript. Key messages, commands, and results are kept in order,
  including dead ends. Routine back and forth is shortened. Secrets are `[REDACTED]`.
  The full raw session log is kept locally by the author.
- **Continues from:** `ai-transcripts/S1-007/2026-11-01-claude-code-iverson.md`

---

## 1. Starting point

S1-007 (PR #31) was merged to `main`. CI ran on the push to `main` and passed.
Lorenzo's PR #30 (`backend/tests/test_target_model.py`) had merged earlier the same day.

```bash
git checkout main
git pull
git log --oneline -3
```

```
d0c97f8 Merge pull request #31 from bdorf04NJIT/feature/S1-007-pr-ci
3168091 ci: add pull request workflow for frontend and backend checks
26342d9 Merge pull request #30 from bdorf04NJIT/feature/target-model
```

## 2. What S1-006 needs

From the story: lint or static analysis, formatting, and unit tests runnable by any developer
from the repo. Formatting must be enforceable, not dependent on editor settings.

Already in place:
- Frontend: ESLint (`npm run lint`), Vitest (`npm test`)
- Backend: pytest

Missing:
- Backend linter and formatter. `docs/coding-standards.md` promises ruff.
- Frontend formatter. `docs/coding-standards.md` promises Prettier.

---

## 3. Dry runs (no repo files changed)

Ruff was installed into the local venv only, and Prettier ran through `npx`.

```powershell
.\.venv\Scripts\python.exe -m pip install ruff
.\.venv\Scripts\python.exe -m ruff --version     # ruff 0.17.3
```

Trial config: 100 character lines, Python 3.12, rule sets `E`, `F`, `I`, `B`, `UP`.

```
ruff check --statistics .
7   E501  line-too-long
5   I001  unsorted-imports
1   B905  zip-without-explicit-strict
Found 13 errors.

ruff format --check .
9 files would be reformatted, 5 files already formatted
```

The one `B905` hit:

```python
# tests/test_target_ownership.py:29
assert {row.id: row.owner_id for row in rows} == dict(zip(ids, ("user-a", "user-b")))
```

Prettier with no semicolons and single quotes, matching the existing code:

```
npx prettier@3 --check "src/**/*.{ts,tsx,css}" "*.{ts,js,json,html}"
Code style issues found in 14 files.
```

### Dead end: every file flagged

All 14 files failed, including ones that looked correctly formatted. Cause: Windows line
endings.

```
git config core.autocrlf        -> true
file frontend/src/App.tsx       -> ... with CRLF line terminators
```

Git converts files to CRLF on Windows checkout. Prettier expects LF by default. CI runs on
Linux, where files are LF. Rerun with `"endOfLine": "auto"`:

| printWidth | Files flagged |
|---|---|
| 80 | 5 |
| 100 | 5 |

Picked 100 to match the backend.

---

## 4. Plan

Branch `feature/S1-006-lint-format`, three commits so config and pure formatting can be
reviewed separately.

1. **Tooling config**
   - `backend/requirements.txt`: add `ruff`
   - `backend/ruff.toml`: line length 100, Python 3.12, rules `E`, `F`, `I`, `B`, `UP`.
     `E501` left to the formatter.
   - `frontend/package.json`: add `prettier` dev dependency, `format` and `format:check` scripts
   - `frontend/.prettierrc.json`: no semicolons, single quotes, printWidth 100, endOfLine auto
   - `frontend/.prettierignore`: `dist`, `package-lock.json`
2. **Formatting only:** run `ruff format`, `ruff check --fix`, and `prettier --write` once.
   Add `strict=True` to the one `zip()` call.
3. **CI:** add `npm run format:check` to the frontend job. Add `ruff check .` and
   `ruff format --check .` to the backend job.

Decision: skip `eslint-config-prettier`. The current ESLint config has no formatting rules,
so ESLint and Prettier cannot conflict. One fewer dependency.

---

## 5. Questions before approving

**Iverson:**
> wait for commit 2, does it re-touches teammates files in what way, just style wise correct?

**Claude:** Yes. It only changes how code looks, never what it does: wrapping long lines,
sorting imports, spacing and blank lines, trailing commas, and CSS and JSON layout.

Example from the dry run, `tests/test_target_ownership.py`:

Before:
```python
@pytest.mark.parametrize("payload", [None, [], {}, {**PAYLOAD, "name": " "}, {**PAYLOAD, "source_url": "file:///etc/passwd"}])
```

After:
```python
@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {**PAYLOAD, "name": " "}, {**PAYLOAD, "source_url": "file:///etc/passwd"}],
)
```

The one real edit is `zip(..., strict=True)`. It raises an error if the two sequences ever
differ in length, instead of silently dropping items. Both have 2 items in that test, so
behavior is unchanged today. Tests run before and after commit 2 to prove it.

Team heads up needed: commit 2 touches files written by Kevin, Connor, and Lorenzo.

---

## 6. Implementation

```bash
git checkout -b feature/S1-006-lint-format
```

### Commit 1: `chore: add ruff and prettier config`

- `backend/requirements.txt`: added `ruff>=0.17,<0.18`. Pinned to a minor range because
  ruff's formatting output can change between minor versions.
- `backend/ruff.toml`: line length 100, `py312`, rules `E`, `F`, `I`, `B`, `UP`, ignore `E501`.
- `frontend/package.json`: `prettier` dev dependency, `format` and `format:check` scripts.
- `frontend/.prettierrc.json` and `frontend/.prettierignore`.

Checks after commit 1, before formatting:

```
ruff check .            -> 6 errors (5 I001, 1 B905)
ruff format --check .   -> 9 files would be reformatted
pytest                  -> 35 passed   (7 new tests from PR #30)
npm run format:check    -> 5 files with style issues
npm run lint            -> exit 0
npm test                -> 9 passed
```

Format checks failing here is expected. Commit 2 fixes them.

### Dead end: lockfile churn

The first `npm install -D prettier@3` changed 71 lines in `package-lock.json`, not just the
Prettier entry. It also removed many `"libc": ["glibc"]` and `"libc": ["musl"]` fields.

Cause: local npm was 10.9. The lockfile had been written by npm 11, which records `libc` so
Linux installs (like CI) pick the right native binary. npm 10 dropped those fields.

Fix: restored the lockfile and reinstalled with npm 11, then amended commit 1 before pushing.

```bash
git show HEAD~1:frontend/package-lock.json > package-lock.json
npx npm@11 install
```

```
frontend/package-lock.json | 17 +++++++++++++++++   (Prettier entry only)
```

### Commit 2: `style: format backend and frontend with ruff and prettier`

```bash
ruff check --fix .        # Found 6 errors (5 fixed, 1 remaining)
# manual: zip(ids, ("user-a", "user-b"), strict=True)
ruff format .             # 9 files reformatted, 5 files left unchanged
npx prettier --write .    # App.test.tsx, App.tsx, index.css, pages/Home.tsx, tsconfig.json
```

14 files changed, 265 insertions, 89 deletions.

Proof it is formatting only, by comparing each backend file's parsed Python structure
(AST) before and after:

| Result | Files |
|---|---|
| Identical | `supabase_auth.py`, `auth.py`, `routes.py`, `services/targets.py`, `conftest.py`, `test_database_config.py` |
| Identical except import order | `test_target_model.py`, `test_auth.py` (an import inside a function was re-sorted) |
| Identical except import order and `strict=True` | `test_target_ownership.py` |

### Step 3 (left uncommitted for review)

`.github/workflows/ci.yml`:

```
frontend -> Check out | Set up Node.js | Install | Lint | Format check | Unit tests | Build
backend  -> Check out | Set up Python | Install | Lint | Format check | Build (syntax check) | Unit tests
```

- Frontend: added `npm run format:check`.
- Backend: added `ruff check .` and `ruff format --check .`.
- Job names unchanged, so required checks in branch protection do not need updating.

---

## 7. Verification

After commit 2, every CI command run locally:

| Command | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 14 files already formatted |
| `python -m compileall -q app` | exit 0 |
| `pytest` | 35 passed |
| `npm run format:check` | All matched files use Prettier code style |
| `npm run lint` | exit 0 |
| `npm test` | 9 passed |
| `npm run build` | built, exit 0 |

---

## 8. Not done in this session

- Commit step 3, push, and open the PR. Waiting on the author's review.
- Team heads up that commit 2 reformats their files. Open branches may need a rebase.
- Root README documenting the lint, format, and test commands is S1-005.
