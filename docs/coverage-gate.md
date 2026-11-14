# Changed-code coverage gate (S2-001)

CI blocks a pull request when the lines it adds or changes are not covered by tests.
The goal is to stop new behavior from landing untested, not to push the overall percentage up.

## Mechanism

- **Backend:** `pytest-cov` writes `coverage.xml`.
- **Frontend:** Vitest with `@vitest/coverage-v8` writes `coverage/cobertura-coverage.xml`.
- **Gate:** [diff-cover](https://github.com/Bachmann1234/diff_cover) compares each report with
  the PR's base branch and checks only the lines the PR changed.

The gate is the **Changed-code coverage gate** step in the `backend` and `frontend` jobs of
[ci.yml](../.github/workflows/ci.yml). It runs on pull requests only.

## Threshold

| Side     | Changed lines that must be covered |
| -------- | ---------------------------------- |
| Backend  | 80%                                |
| Frontend | 70%                                |

If either side falls below its threshold, that job fails and the PR cannot merge.

## Exclusions

- Only `backend/app/` (backend) and `frontend/src/**/*.{ts,tsx}` (frontend) are measured.
- Test files (`backend/tests/`, `*.test.ts(x)`) are not measured.
- Files with no executable code (docs, CSS, config, workflows) are ignored by diff-cover.
- No `pragma: no cover` or `v8 ignore` comments are used. Don't add any without team agreement.

## Run it locally

Commit or stage your changes first, since diff-cover compares against `main`.

```bash
# Backend (venv active)
cd backend
pytest --cov=app --cov-report=xml
diff-cover coverage.xml --compare-branch=main --fail-under=80

# Frontend (Node 20+; Vitest crashes on Node 18)
cd frontend
npm run test:coverage
diff-cover coverage/cobertura-coverage.xml --compare-branch=main --fail-under=70
```

`diff-cover` comes with the backend `requirements.txt`. If the frontend tests fail to start,
diff-cover reads the old report and may pass wrongly. Check that the tests actually ran.

## Proof the gate works

A branch containing only untested new files (`coverage_probe.py`, `coverageProbe.ts`) fails
both gates at 0% changed-line coverage.
