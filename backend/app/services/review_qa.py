"""Connects the Q&A interface to the system prompt (S2-013) and Gemini.

This is the wiring between the existing prompt builder and the model: take a question
for an owned target, read that target's persisted reviews (via the existing owner-scoped
query), build the system prompt, send prompt + reviews + question to Gemini, and return
the model's parsed {status, answer, review_ids} reply.

Review-context architecture (S2-010)
-------------------------------------
Context for a question is built from the *persisted* reviews of the *one* target named
in the request URL, scoped to the *authenticated* owner. The team's explicit choice of
retrieval strategy is: **supply the target's reviews directly, bounded by a cap** — no
relevance ranking, RAG, or vector search. For this product the per-target dataset is
small (Google Maps review sets, ingested with a bounded page count), so sending the
dataset as-is is simpler, deterministic, and avoids extra infrastructure and failure
modes. It is a defensible fit for the dataset size rather than a placeholder.

Because the context is sent to an external model, it must be bounded in two ways:

- ``MAX_REVIEWS`` caps how many reviews are selected (newest first, via
  ``qa_context_reviews``). A stable order makes the selection reproducible.
- ``MAX_CONTEXT_CHARS`` caps the total characters of review text placed in the prompt.
  A handful of very long reviews can blow the model's input budget even under the row
  cap, so ``_reviews_block`` stops adding reviews once the budget would be exceeded.

These limits are fixed code constants, not configuration: the bound is required for the
Q&A path to stay within model token limits and keep calls fast and affordable, so it
must not depend on a deployment remembering to set an env var. When a target has more
reviews or longer text than the budget allows, the most recent reviews that fit are used
and the rest are omitted; the answer is therefore based on a recent, bounded sample
rather than the entire history. (The ``answer_question`` parameters exist so tests can
exercise the bounds directly; production always uses these constants.)

Why newest-first (and its tradeoff)
    The ordering only matters when a target exceeds the cap; below it, every review is
    included and order is irrelevant. For these datasets that is the expected case, so
    the cap is a rare-case safety fallback rather than a routine filter. When it does
    trigger, keeping the newest reviews favors the current state of a business and
    matches the order already used by the review-listing endpoint. The known cost is
    that dropping the oldest reviews weakens time/trend questions ("has it improved over
    time?", "what did early customers say?") and can skew sentiment toward a recent
    period. Alternatives considered and rejected for now: a representative/random sample
    across the time range (better for general-sentiment questions, worse reproducibility),
    rating-stratified selection (guarantees both praise and complaints survive the cap,
    more complexity), and oldest-first (better for history, worse for "current state").
    If targets routinely exceed the cap, revisit this choice or raise the cap.

Scoping (S2-010 guarantees) is unchanged and enforced two ways: ``find_owned_target``
rejects a missing/foreign target with NotFound, and ``qa_context_reviews`` carries the
``owner_id``/``target_id`` filter in the SQL itself. There is no server-side "active
target" state, so a previously selected target cannot leak into a later question — the
target is read only from this request's URL on every call.
"""

import json
from html import escape

from sqlalchemy.orm import Session

from ..errors import QaUnavailable, ValidationError
from .qa_prompt import OUT_OF_SCOPE, RESPONSE_STATUSES, build_system_prompt
from .review_summary import qa_context_reviews
from .targets import find_owned_target

# Fixed bounds on the review context sent to the Q&A model (S2-010). Kept as code
# constants, not configuration, so the limit always applies regardless of environment.
# Chosen to stay comfortably within the fallback models' input limits while covering a
# typical target's dataset.
#
# Two limits because they bound different axes:
#   MAX_REVIEWS       caps the *count* of reviews (protects the query and the common case
#                     as a target accumulates reviews; applied newest-first).
#   MAX_CONTEXT_CHARS caps the *size* of the prompt. 200 short reviews are tiny, but 200
#                     long ones can still exceed the model's input budget, so this is the
#                     backstop. It is a character count used as a cheap proxy for tokens
#                     (~4 chars/token for English) and is intentionally conservative, to
#                     avoid running the model's tokenizer in the request path.
# An oversized request would return HTTP 400 from Gemini, which the adapter treats as
# non-retryable and surfaces as QaUnavailable -- a dead end for the user. These bounds
# make that impossible rather than merely documenting that it can happen.
MAX_REVIEWS = 200
MAX_CONTEXT_CHARS = 120_000


def _question(payload):
    text = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(
            "Ask a question about these reviews.", fields={"question": "required"}
        )
    return text.strip()


def _reviews_block(reviews, *, max_chars=None):
    """Render reviews as an XML-ish block, bounded by an optional character budget.

    Returns ``(block, sent_ids)``: the block text and the ids of the reviews actually
    placed in it, in order. The ids are what the model's citations are checked against.

    Reviews arrive newest-first. When ``max_chars`` is set, reviews are added until the
    next one would push the accumulated review text over the budget, keeping the most
    recent reviews that fit. The budget counts review text so the cap is about model
    input size; the first review is always included so the block is never empty.
    """
    lines = ["<reviews>"]
    sent_ids = []
    used_chars = 0
    for index, review in enumerate(reviews):
        text = escape((review.text or "").strip())
        if max_chars is not None and index > 0 and used_chars + len(text) > max_chars:
            break
        used_chars += len(text)
        sent_ids.append(str(review.id))
        lines.append(
            f'  <review id="{escape(str(review.id), quote=True)}" rating="{review.rating}">{text}</review>'
        )
    lines.append("</reviews>")
    return "\n".join(lines), sent_ids


def _parse_reply(reply, sent_ids):
    """Check the model's reply before it reaches the user (S2-011).

    The answer must stay tied to the reviews we actually supplied, so the model's
    output is not trusted as-is:

    - ``status`` must be one of the prompt's statuses and ``answer`` must be non-empty
      text. Anything else means the model didn't follow the format, which is surfaced
      as a transient failure (503) rather than shown to the user.
    - ``review_ids`` keeps only ids that were in the supplied <reviews> block, as
      strings, without duplicates, in the model's order. Ids the model invented (or
      reviews dropped by the context budget) are removed so they can't be shown as
      evidence. An out-of-scope decline never cites reviews.

    If an "answered" reply cites no valid reviews, the answer is still returned with an
    empty ``review_ids``; the UI then shows the answer without an evidence count.
    """
    try:
        data = json.loads(reply)
    except (ValueError, TypeError) as exc:
        raise QaUnavailable() from exc
    if not isinstance(data, dict):
        raise QaUnavailable()

    status = data.get("status")
    answer = data.get("answer")
    if status not in RESPONSE_STATUSES or not isinstance(answer, str) or not answer.strip():
        raise QaUnavailable()

    cited = data.get("review_ids")
    allowed = set(sent_ids)
    review_ids = []
    if status != OUT_OF_SCOPE and isinstance(cited, list):
        for raw in cited:
            if isinstance(raw, (str, int)) and not isinstance(raw, bool):
                review_id = str(raw).strip()
                if review_id in allowed and review_id not in review_ids:
                    review_ids.append(review_id)

    return {
        "status": status,
        "answer": answer.strip(),
        "review_ids": review_ids,
        "reviews_considered": len(sent_ids),
    }


def answer_question(
    engine,
    gemini,
    *,
    owner_id,
    target_id,
    payload,
    max_reviews=MAX_REVIEWS,
    max_context_chars=MAX_CONTEXT_CHARS,
):
    """Answer one question about an owned target's reviews using the prompt + Gemini.

    ``max_reviews`` and ``max_context_chars`` bound the review context supplied to the
    model (see the module docstring for the rationale and the architectural decision).
    """
    question = _question(payload)

    with Session(engine) as session:
        # Reuse the existing ownership check: a missing or foreign target raises NotFound.
        target = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        name, platform = target.name, target.platform
        # Owner+target-scoped, newest-first, capped at max_reviews. Ownership lives in
        # the query, so the cap cannot widen access to another target's reviews.
        reviews = session.scalars(
            qa_context_reviews(owner_id=owner_id, target_id=target_id, limit=max_reviews)
        ).all()

    if not reviews:
        raise ValidationError("This target has no reviews to answer from yet.")

    system_prompt = build_system_prompt(target_name=name, platform=platform)
    reviews_block, sent_ids = _reviews_block(reviews, max_chars=max_context_chars)
    user_content = f"Question: {question}\n\n{reviews_block}"

    reply = gemini.answer(system_prompt=system_prompt, user_content=user_content)

    # The prompt instructs the model to return only a JSON object with these fields.
    # _parse_reply rejects malformed replies (503) and keeps only citations of reviews
    # that were actually supplied.
    return _parse_reply(reply, sent_ids)
