# ReviewLens AI-Assisted Development and Review

**AI-generated code is team-authored code.** It follows the same standards, reviews, tests, and Definition of Done as code written by hand. The developer who submits it is responsible for understanding it.

## AI tools we use

- **Claude Code** and **Claude** for implementation, refactoring, and tests.
- **Gemini** for explanations and debugging.

Other tools may be used if the developer follows this document.

## Context to give AI tools

Give the tool enough context to strictly follow our rules rather than generic defaults. For any task, supply:

- The Jira story rule IDs (for example, S1-BR-008).
- The relevant context documents:
  - `coding-standards.md` (S1-001)
  - `ui-ux-standards.md` (S1-002)
  - `data-and-security-guardrails.md` (S1-003)
  - this document (S1-004)
- The existing files the change touches, so the tool follows current patterns.

Never paste secrets, `.env` contents, access tokens, or real user data into an AI tool.

## Reviewing generated code

Before opening a pull request, the author must:

- Read every generated line and be able to explain it.
- Remove dead code and any speculative features that are outside the story's scope.
- Check that the code follows our conventions for structure, logging, errors, and API responses rather than the tool's defaults.

Pull requests that contain AI-generated code must say so in the description. A teammate other than the author must approve every pull request.

## Validating dependencies and APIs

AI tools sometimes suggest packages or functions that don't exist or are out of date.

- Confirm the package exists on PyPI or npm under the exact name, is  maintained, and has an acceptable license.
- Check the call against the official documentation for the version we use.
- Add dependencies to the backend dependency file or `frontend/package.json`, commit `package-lock.json`, and explain the addition in the pull request.
- New dependencies must pass pip-audit / npm audit in CI.
- External services such as SerpApi, Supabase, and Gemini are called only through `backend/app/adapters/`.

## Testing generated code

Generated code must pass CI and meet `coding-standards.md`: each change needs a happy-path test and a negative test.

- Review generated tests (pytest and Vitest) as carefully as generated code.
- Confirm each test fails when the behavior it checks is broken, for example by temporarily removing an ownership check.
- Use fixtures and mocks, never live services.
- Never weaken, skip, or delete a failing test to make generated code pass.

## Keeping AI transcripts

The project requires complete AI development transcripts in the `/ai-transcripts` directory.

- Save transcripts as `/ai-transcripts/<story-id>/<date>-<tool>-<author>.md`.
- Export the full session, including dead ends and failed approaches.
- Redact secrets as `[REDACTED]`. Make no other edits.
- Commit transcripts in the same pull request as the code they produced.
- For inline completion tools that do not produce transcripts, note the tool's use in the pull request description.

## Changes that need extra security review

If generated code touches any of these, a second reviewer checks it against `data-and-security-guardrails.md` before approval.

- **Authentication:** token verification, session handling, or route protection (S1-BR-004).
- **Ownership:** any query or endpoint that reads or changes user-owned data (S1-BR-008).
- **Secrets and configuration:** environment variables, `.env.example`, `VITE_*` variables, logging, or error messages (S1-BR-011).
- **Ingestion:** code that calls SerpApi or parses external review data.
- **Schema:** migrations and model relationships.
- **CI configuration:** changes to GitHub Actions workflows or branch protection.
- **AI prompts and context:** in later sprints, code that builds LLM prompts or selects which reviews reach the model.

A generated change that removes or loosens an ownership check, validation, or test is a red flag, even if it makes the code work.
