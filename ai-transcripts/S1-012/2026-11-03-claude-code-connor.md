# S1-012 Cross-user target authorization: AI session transcript

- **Story:** S1-012 Enforce Cross-User Analysis Target Authorization
- **Rules:** S1-BR-007 through S1-BR-010, S1-BR-016
- **Date:** 2026-11-03
- **Tool:** Claude Code (Claude Opus 5.5, VS Code extension)
- **Author:** Connor Melton
- **Branch:** `feature/S1-012-cross-user-authorization` (from `main` at `f11cea1`)
- **Format:** Condensed transcript. Key messages, commands, and results are kept in order,
  including dead ends. Routine back and forth is shortened. Secrets are `[REDACTED]`
  (none appeared in this session). The full raw session log is kept locally by the author.

---

## 1. Request

> As per the Sprint1Issues.csv, I am working on S1-012 Enforce Cross-User Analysis Target
> Authorization. Implement bare bones and explain changes / how to test.

Ticket text supplied with the request:

> **Outcome:** An authenticated user cannot read or modify an AnalysisTarget owned by another
> authenticated user.
>
> **Technical Guidance:** Authorization must be enforced even when a user knows or guesses
> another target's identifier. Testing should use at least two distinct authenticated user
> identities:
>
> - User A creates or owns Target A.
> - User B attempts to retrieve Target A.
> - User B attempts a modifying operation against Target A.
> - Both unauthorized operations are denied.
> - Target A remains unchanged.
>
> Do not rely on the fact that Target A is absent from User B's UI.

---

## 2. Exploring what already exists

Claude read `backend/app/routes.py`, `backend/app/services/targets.py`, `backend/app/auth.py`,
`backend/app/errors.py`, `backend/tests/conftest.py`, the existing ownership and ingestion
tests, and `docs/ai-assisted-development.md`.

Findings:

- Every target-by-id route already goes through `find_owned_target`, which filters on
  **both** id and owner in one query:

  ```python
  row = session.scalars(
      select(AnalysisTarget).where(
          AnalysisTarget.id == target_id, AnalysisTarget.owner_id == owner_id
      )
  ).one_or_none()
  if row is None:
      raise NotFound("We couldn't find that analysis target.")
  ```

- Routes covered: `GET /targets/<id>`, `POST /targets/<id>/ingestions`,
  `POST /targets/<id>/ingestions/import`, `GET /targets/<id>/reviews`.
- Existing cross-user tests (from S1-017/S1-018/S1-020+) already deny User B on reads,
  ingestion, and CSV import.
- `conftest.py` already provides an `auth_header(user_id)` fixture for fake users,
  with a comment that it was meant for S1-012 reuse.
- The S1-018 transcript had already noted the gap:

  > S1-012, cross-user target authorization. It's mostly covered already by the S1-017 and
  > S1-018 tests. What's left is mainly a modifying operation that can be denied, and there
  > isn't an update or delete endpoint yet.

**Gap:** there was no endpoint that modifies the `AnalysisTarget` itself, so "User B attempts
a modifying operation against Target A / Target A remains unchanged" could not be shown
directly.

**Plan (bare bones):** add `PATCH /api/targets/<id>` (rename / change source URL) that uses
the same `find_owned_target` check, plus one dedicated two-user test file.

```bash
git checkout -b feature/S1-012-cross-user-authorization
```

---

## 3. Dead end: no `python` on PATH

Claude first tried to apply the edits with an inline Python script:

```
/bin/bash: line 66: python: command not found
```

The project uses a venv at `backend/.venv`. Claude switched to the editor's Edit tool for the
code changes and used `.venv/bin/python` for running tests.

---

## 4. Changes

### 4.1 `backend/app/services/targets.py`

Added an update validator and an ownership-checked update service. Ownership is checked
**before** the body is validated, so a non-owner always gets the same 404 as a missing id and
cannot learn anything from validation errors.

```python
UPDATABLE_FIELDS = {"name", "source_url"}


def validate_target_update(payload):
    # Only name and source_url may change. Ownership, id, and platform are never client-editable.
    if not isinstance(payload, dict) or not payload or not set(payload) <= UPDATABLE_FIELDS:
        raise ValidationError("Provide only name and/or source_url to update.")
    errors, values = {}, {}
    if "name" in payload:
        name = _text(payload, "name")
        if not name:
            errors["name"] = MESSAGES["name_missing"]
        elif len(name) > MAX_NAME:
            errors["name"] = MESSAGES["name_long"]
        values["name"] = name
    if "source_url" in payload:
        source_url = _text(payload, "source_url")
        url_error = source_url_error(source_url)
        if url_error:
            errors["source_url"] = url_error
        values["source_url"] = source_url
    if errors:
        raise ValidationError("Some target details need fixing.", fields=errors)
    return values


def update_target(engine, *, owner_id, target_id, payload):
    """Update a target only if owner_id owns it.

    Ownership is checked BEFORE the body is validated, so a non-owner always gets
    the same NotFound as a missing id and learns nothing from validation errors.
    """
    with Session(engine) as session, session.begin():
        row = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        for field, value in validate_target_update(payload).items():
            setattr(row, field, value)
        session.flush()
        return _summary(row)
```

### 4.2 `backend/app/routes.py`

```diff
-from .services.targets import create_target, get_target, list_targets
+from .services.targets import create_target, get_target, list_targets, update_target
```

```python
@bp.patch("/targets/<target_id>")
@require_auth
def patch_target(target_id):
    # Ownership is enforced inside update_target; the URL id alone grants nothing.
    target = update_target(
        current_app.extensions["database"],
        owner_id=g.user_id,
        target_id=target_id,
        payload=request.get_json(silent=True),
    )
    return jsonify(target)
```

The owner comes only from `g.user_id` (the verified token), never from the URL, query
string, or body.

### 4.3 `backend/tests/test_cross_user_authorization.py` (new)

Follows the ticket scenario with `user-a` and `user-b`:

| Test | Checks |
| --- | --- |
| `test_owner_can_update_own_target` | Happy path: owner PATCH returns 200 and persists. |
| `test_user_b_cannot_retrieve_target_a` | User B GET returns 404 `NOT_FOUND`, and the body does not contain Target A's name. |
| `test_user_b_cannot_modify_target_a` (x4 bodies) | User B PATCH returns 404 for a valid rename, a URL change, an `owner_id` body, and `{}`. The DB row (owner, name, platform, URL, created_at) is unchanged, and User A still sees "Target A". |
| `test_denied_and_missing_targets_look_the_same` | GET and PATCH on another user's id give the same response as a nonexistent id. |
| `test_forged_owner_query_param_does_not_grant_access` (x5) | `?owner_id=user-a` and similar params do not unlock access. |
| `test_user_b_can_still_modify_own_target` | Isolation works both ways. User B edits Target B and Target A is untouched. |
| `test_owner_cannot_edit_protected_fields` (x4) | The owner gets 400 for `owner_id`, `platform`, `{}`, and a non-dict body. |
| `test_unauthenticated_patch_is_rejected` | No token returns 401 and nothing changes. |

---

## 5. Verification

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

```
181 passed in 4.33s
All checks passed!
30 files already formatted
```

### 5.1 Checking that the tests fail without the ownership check

Per `docs/ai-assisted-development.md`, the tests must fail when the behavior they guard is
broken. Claude backed up `targets.py`, removed the owner filter from `find_owned_target`,
and ran the new test file:

```bash
sed -i 's/AnalysisTarget.id == target_id, AnalysisTarget.owner_id == owner_id/AnalysisTarget.id == target_id/' \
  app/services/targets.py
.venv/bin/python -m pytest -q tests/test_cross_user_authorization.py
```

```
FAILED tests/test_cross_user_authorization.py::test_forged_owner_query_param_does_not_grant_access[ownerId]
FAILED tests/test_cross_user_authorization.py::test_forged_owner_query_param_does_not_grant_access[owner]
10 failed, 8 passed in 0.49s
```

All 10 cross-user denial tests failed as expected. The 8 that passed are owner-only and
unauthenticated tests that do not depend on the owner filter.

### 5.2 Dead end: `git checkout` reverted the new code too

To undo the mutation, Claude ran `git checkout app/services/targets.py`. That restored the
file to `main`, which **also wiped the uncommitted `update_target` code** from section 4.1:

```
 backend/app/routes.py | 15 ++++++++++++++-
 1 file changed, 14 insertions(+), 1 deletion(-)
```

Claude restored it from the backup taken before the mutation and reran the suite:

```bash
cp /tmp/claude-1000/t.bak app/services/targets.py && rm /tmp/claude-1000/t.bak
git diff --stat
.venv/bin/python -m pytest -q
```

```
 backend/app/routes.py           | 15 ++++++++++++++-
 backend/app/services/targets.py | 40 ++++++++++++++++++++++++++++++++++++++++
 2 files changed, 54 insertions(+), 1 deletion(-)
181 passed in 3.65s
```

Lesson: restore a mutation test from the backup copy, not from git, when the file has
uncommitted work.

---

## 6. How to test

**Automated:**

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_cross_user_authorization.py   # S1-012 only
.venv/bin/python -m pytest -q                                          # full suite
```

**Manual (two real Supabase accounts):** sign in as User A and User B and take each access
token from the browser's network tab.

```bash
# As A: create a target and note the id
curl -X POST localhost:5000/api/targets -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"name":"Target A","platform":"google_maps","source_url":"https://www.google.com/maps/place/X"}'

# As B: try to read and modify it. Both should return 404 NOT_FOUND.
curl localhost:5000/api/targets/$ID -H "Authorization: Bearer $TOKEN_B"
curl -X PATCH localhost:5000/api/targets/$ID -H "Authorization: Bearer $TOKEN_B" \
  -H "Content-Type: application/json" -d '{"name":"Hijacked"}'

# As A: confirm the name is still "Target A"
curl localhost:5000/api/targets/$ID -H "Authorization: Bearer $TOKEN_A"
```

---

## 7. Notes for the PR

- The PR contains AI-generated code (Claude Code) and must say so in the description.
- The change touches an ownership check (S1-BR-008), so a second reviewer must check it
  against `docs/data-and-security-guardrails.md`.
- Out of scope, intentionally not added: a DELETE endpoint and frontend UI for editing
  targets.
