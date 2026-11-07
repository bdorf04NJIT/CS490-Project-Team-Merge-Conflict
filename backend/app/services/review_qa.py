"""Connects the Q&A interface to the system prompt (S2-013) and Gemini.

This is the wiring between the existing prompt builder and the model: take a question
for an owned target, read that target's persisted reviews (via the existing owner-scoped
query), build the system prompt, send prompt + reviews + question to Gemini, and return
the model's parsed {status, answer, review_ids} reply.

It deliberately reuses existing ownership and review-fetch code and adds no new retrieval
strategy, error semantics, or security layer beyond what is already in the app.
"""

import json
from html import escape

from sqlalchemy.orm import Session

from ..errors import QaUnavailable, ValidationError
from .qa_prompt import build_system_prompt
from .review_summary import active_reviews
from .targets import find_owned_target


def _question(payload):
    text = payload.get("question") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(
            "Ask a question about these reviews.", fields={"question": "required"}
        )
    return text.strip()


def _reviews_block(reviews):
    lines = ["<reviews>"]
    for review in reviews:
        text = escape((review.text or "").strip())
        lines.append(
            f'  <review id="{escape(str(review.id), quote=True)}" rating="{review.rating}">{text}</review>'
        )
    lines.append("</reviews>")
    return "\n".join(lines)


def answer_question(engine, gemini, *, owner_id, target_id, payload):
    """Answer one question about an owned target's reviews using the prompt + Gemini."""
    question = _question(payload)

    with Session(engine) as session:
        # Reuse the existing ownership check: a missing or foreign target raises NotFound.
        target = find_owned_target(session, owner_id=owner_id, target_id=target_id)
        name, platform = target.name, target.platform
        reviews = session.scalars(active_reviews(owner_id=owner_id, target_id=target_id)).all()

    if not reviews:
        raise ValidationError("This target has no reviews to answer from yet.")

    system_prompt = build_system_prompt(target_name=name, platform=platform)
    user_content = f"Question: {question}\n\n{_reviews_block(reviews)}"

    reply = gemini.answer(system_prompt=system_prompt, user_content=user_content)

    # The prompt instructs the model to return only a JSON object with these fields.
    # A non-JSON or malformed reply means the model didn't cooperate; treat it as a
    # transient assistant failure (503) rather than a 500 from an uncaught parse error.
    try:
        data = json.loads(reply)
    except (ValueError, TypeError) as exc:
        raise QaUnavailable() from exc
    if not isinstance(data, dict):
        raise QaUnavailable()
    return {
        "status": data.get("status"),
        "answer": data.get("answer"),
        "review_ids": data.get("review_ids", []),
    }
