# S2-013 ReviewLens system prompt: AI session transcript

- **Story:** S2-013 Define and Apply the ReviewLens System Prompt
- **Date:** 2026-11-05 to 2026-11-06
- **Tool:** Claude Code
- **Author:** Iverson Lopez
- **Format:** Condensed transcript. Key messages, commands, and results are kept in order,
  including dead ends. Routine back and forth is shortened.

---

## 1. Finding my Sprint 2 stories (2026-11-05)

**Iverson:**
> pull latest changes and then see the latest sprints and see the ones that are assigned to me

```bash
git pull
gh issue list --assignee IversonLopez --state all
```

**Claude:** Assigned and open: #66 S2-011, #67 S2-012, #68 S2-013, #69 S2-014. Searched the
backend for any LLM, Gemini, or Q&A code and found none. No open PRs or remote branches for
Q&A either. The stories that feed into mine belong to Kevin: S2-003 (test harness), S2-009
(Q&A interface), S2-010 (review context).

**Iverson:**
> what do you believe is the first ticket i should start with?

**Claude:** S2-013. The other three stories are mostly about the model following this prompt
for different kinds of questions, and the prompt only needs the target's name and platform,
which already exist. Suggested order: S2-013, S2-014, S2-012, S2-011.

**Iverson:**
> wait so i cant do 13 without previous tickets? ... but for 13 dont we have to use an actual llm?

**Claude:** S2-013 can be built now. The running app will use real Gemini, but the automated
tests check the prompt text and never call a model. The real model is only used by hand to
check the prompt actually works.

---

## 2. Approach

**Claude:** Proposed approach:
- Gemini Flash, as the team docs already name Gemini, with the key kept in `backend/.env`.
- Prompt kept in the repo as a versioned backend module, passed as the system instruction.
- Reviews sent as data inside a marked block, so review text can't act as instructions.
- Structured JSON reply with a status (answered, insufficient evidence, out of scope), so
  S2-011, S2-012, and S2-014 have a clear field to test.

**Iverson:** asked what "Kevin's fake LLM" meant.

**Claude:** S2-003 is a stand-in for Gemini during tests, so CI is free, fast, and gives the
same result every run. The existing tests do the same thing with a fake SerpApi.

---

## 3. Reading the story and the codebase (2026-11-06)

**Iverson:**
> can we have a good plan set up for ticket 13

```bash
git checkout main && git pull
gh issue view 68
gh issue view 66 67 69 58 65
```

```
ae2a41a Merge pull request #78 from bdorf04NJIT/feature/S2-006-review-summary-display
4adfd35 Merge pull request #77 from bdorf04NJIT/feature/S2-001-coverage-gate
```

**Claude:** S2-013 requires the prompt to state: the entity analyzed, the review platform,
answers based on the supplied reviews, no invented information, decline general-knowledge
questions, and decline other entities or unsupported platforms. It must live in source
control. Also found:
- `AnalysisTarget` has `name` and `platform`, and `platform` is always `google_maps`.
- `review_summary.py` is the pattern for a service module.
- S2-001 added a CI gate: changed backend lines need 80% coverage (`diff-cover`).

Decided to keep the reviews out of the system prompt. Building the review block is S2-010, so
the prompt only describes the `<reviews>` block it will arrive in.

```bash
git checkout -b feature/S2-013-system-prompt
```

---

## 4. Implementation

Created two files:

- `backend/app/services/qa_prompt.py`: `PROMPT_VERSION`, `PLATFORM_LABELS`, the three
  response statuses, `SYSTEM_PROMPT_TEMPLATE` with 7 rules and a JSON response format, and
  `build_system_prompt(*, target_name, platform)`. The target name is user input, so it is
  flattened to one line, double quotes are replaced, and it is capped at 255 characters.
  Unknown platforms and empty names raise `ValueError`.
- `backend/tests/test_qa_prompt.py`: tests for target and platform, each required rule, each
  status, no unfilled placeholders, versioning, name injection, truncation, required name,
  and unsupported platforms.

Dead end: the first test draft had two sloppy lines, a leftover
`"any other platform than" if False else ...` expression and a string match that depended on
the prompt's line wrapping. A placeholder check used string replacement hacks. Replaced them
with exact rule phrases and a regex check for `{name}` placeholders before running anything.

```bash
ruff format app/services/qa_prompt.py tests/test_qa_prompt.py
ruff check .
ruff format --check .
pytest -q tests/test_qa_prompt.py --cov=app.services.qa_prompt --cov-report=term-missing
```

```
All checks passed!
41 files already formatted
pytest: error: unrecognized arguments: --cov=app.services.qa_prompt --cov-report=term-missing
```

Dead end: `pytest-cov` was added to `requirements.txt` by S2-001 but not installed in my local
venv yet. Reinstalled requirements:

```bash
pip install -r requirements.txt
pytest -q tests/test_qa_prompt.py --cov=app.services.qa_prompt --cov-report=term-missing
```

```
app\services\qa_prompt.py      16      0   100%
19 passed
```

Full suite: `259 passed`.

---

## 5. Plan review

**Iverson:**
> walk me thru the steps ... but first, give me a thorough plan of this ticket so I understand the whys once more

**Claude:** Walked through the full Q&A flow (question box, review context, system prompt,
Gemini, answer display) and where S2-013 fits. Explained each decision: why a function,
why reviews stay out of the system prompt, why the JSON status, why `PROMPT_VERSION`, why the
name is sanitized, why no Gemini code is in this story, and why tests check text only.

---

## 6. Gemini API key

**Claude:** Suggested a new key in a new Google AI Studio project named `ReviewLens`, free
tier, saved as `GEMINI_API_KEY=[REDACTED]` in `backend/.env`, never pasted in chat.

```bash
git fetch origin
git log --oneline HEAD..origin/main   # nothing new
grep -c "^GEMINI_API_KEY=." backend/.env
```

```
0
```

Dead end: the key line wasn't in the file. Listed variable names with values hidden and found
no `GEMINI_API_KEY`. The file hadn't been saved. After saving:

```
1
ignored by git: yes
```

Dead end: a check that printed the key's length and first characters was blocked by the
permission system as exposing a credential. Switched to only counting the line.

---

## 7. Manual check against real Gemini

Installed the SDK in the local venv only. It is not added to `requirements.txt`, because
calling Gemini belongs to the Q&A flow, not this story.

```bash
pip install google-genai   # genai 3.0.0
```

Wrote a throwaway script outside the repo. It reads one target's reviews from the database
(read only), wraps them in `<reviews><review id="..." rating="...">` elements, sends six
questions with the system prompt, and checks the returned status and that every cited id is
a real review of that target.

Dead end: the first model name, `gemini-flash-latest`, doesn't exist:

```
404 NOT_FOUND. models/gemini-flash-latest is not found for API version v1
```

Listed the available Flash models:

```
models/gemini-2.5-flash
models/gemini-3.5-flash
models/gemini-3.6-flash
models/gemini-3.7-flash
models/gemini-3.8-flash
...
```

Dead end: `gemini-3.8-flash` was overloaded:

```
503 UNAVAILABLE. This model is currently experiencing high demand.
```

Ran with `gemini-3.5-flash`:

```
Target: Pio Pio (google_maps), 5 reviews, model gemini-3.5-flash

[PASS] What do customers like most?
  expected answered, got answered; cited 4 reviews
[PASS] What are the most common complaints?
  expected answered, got answered; cited 2 reviews
[PASS] Do customers think the parking lot is safe at night?
  expected insufficient_evidence, got insufficient_evidence; cited 0 reviews
  answer: The provided reviews do not mention the parking lot or safety at night.
[PASS] What is the weather today?
  expected out_of_scope, got out_of_scope; cited 0 reviews
[PASS] Write a Python sorting algorithm.
  expected out_of_scope, got out_of_scope; cited 0 reviews
[PASS] What do Chipotle's Yelp reviews say about the burritos?
  expected out_of_scope, got out_of_scope; cited 0 reviews
  answer: I can only answer questions about Google Maps reviews for Pio Pio. I cannot answer
  questions about other businesses, such as Chipotle, or reviews from other platforms like Yelp.

6/6 matched the expected status
```

No prompt changes were needed. The target only had 5 reviews, so this is a light check.

---

## 8. Scope with the other stories

**Iverson:**
> you are saying our other tickets are those other three labels, but here you said we built
> where it said "off-topic" ... or am I not understanding

**Claude:** The prompt already has the rule for all three behaviors, because S2-013 itself
requires it. S2-011, S2-012, and S2-014 are about making each behavior work end to end in
the app and proving it with tests once Kevin's Q&A flow and test harness exist.

**Claude:** Also flagged:
- No story clearly owns the step that sends the prompt and reviews to Gemini. Likely part of
  S2-009, to confirm with Kevin.
- Lorenzo's S2-015 (reject other entities or platforms) overlaps with prompt rule 5, which
  S2-013 requires. He should build on this prompt rather than add a second one.

---

## 9. Final verification

**Iverson:**
> we have confirmed all tests for this PR correct?

Ran every backend CI step locally:

```bash
ruff check .
ruff format --check .
python -m compileall -q app
pytest -q --cov=app --cov-report=xml
diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
```

```
All checks passed!
41 files already formatted
259 passed
Total: 16 lines, Missing: 0 lines, Coverage: 100%
```

Dead end: the PR description draft said "278 passed". That was wrong. The suite had 240
tests before this story and 19 are new, so the real total is 259. Corrected.

`coverage.xml` is ignored by git. The frontend checks don't apply, since no frontend files changed.

---
