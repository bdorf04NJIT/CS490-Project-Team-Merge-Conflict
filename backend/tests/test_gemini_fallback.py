"""Fallback behavior of the Gemini adapter, verified without calling the real model.

The adapter tries an ordered chain of models and only falls back on transient failures
(503/504 or an empty reply). Quota/missing/auth errors are surfaced at once. These tests
drive that logic by overriding the single-model call with scripted outcomes, so no
network request is made.
"""

import pytest
from google.genai import errors as genai_errors

from app.adapters.gemini_source import FALLBACK_MODELS, GeminiReviewAnswerer
from app.errors import QaUnavailable


def api_error(code):
    """Build a real google-genai APIError carrying an HTTP-style status code."""
    err = genai_errors.APIError.__new__(genai_errors.APIError)
    err.code = code
    err.message = f"simulated {code}"
    err.status = str(code)
    err.details = None
    return err


class ScriptedAnswerer(GeminiReviewAnswerer):
    """Adapter whose per-model call follows a scripted list of outcomes.

    Each outcome is either a string (the model's reply text), '' (empty reply),
    or an Exception to raise. Records which models were attempted, in order. Only
    ``_generate`` is overridden, so the real ``answer`` fallback logic is exercised
    (``genai.Client`` constructs without any network call; the network only happens
    inside ``_generate``, which this replaces).
    """

    def __init__(self, outcomes, *, model=None):
        super().__init__(api_key="k", model=model)
        self._outcomes = list(outcomes)
        self.attempted = []

    def _generate(self, client, model, user_content, config):
        self.attempted.append(model)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_first_model_success_skips_the_rest():
    a = ScriptedAnswerer(["the answer"])
    assert a.answer(system_prompt="s", user_content="u") == "the answer"
    assert a.attempted == [FALLBACK_MODELS[0]]


def test_overloaded_first_model_falls_back_to_next():
    a = ScriptedAnswerer([api_error(503), "second model answer"])
    assert a.answer(system_prompt="s", user_content="u") == "second model answer"
    assert a.attempted == list(FALLBACK_MODELS[:2])


def test_504_also_triggers_fallback():
    a = ScriptedAnswerer([api_error(504), "ok"])
    assert a.answer(system_prompt="s", user_content="u") == "ok"
    assert len(a.attempted) == 2


def test_empty_reply_triggers_fallback():
    a = ScriptedAnswerer(["", "non-empty"])
    assert a.answer(system_prompt="s", user_content="u") == "non-empty"
    assert len(a.attempted) == 2


def test_quota_error_is_not_retried():
    a = ScriptedAnswerer([api_error(429), "should not reach"])
    with pytest.raises(QaUnavailable):
        a.answer(system_prompt="s", user_content="u")
    # Stopped at the first model; no fallback on a quota error.
    assert a.attempted == [FALLBACK_MODELS[0]]


def test_missing_model_error_is_not_retried():
    a = ScriptedAnswerer([api_error(404), "should not reach"])
    with pytest.raises(QaUnavailable):
        a.answer(system_prompt="s", user_content="u")
    assert a.attempted == [FALLBACK_MODELS[0]]


def test_all_models_overloaded_raises_qa_unavailable():
    a = ScriptedAnswerer([api_error(503)] * len(FALLBACK_MODELS))
    with pytest.raises(QaUnavailable):
        a.answer(system_prompt="s", user_content="u")
    assert a.attempted == list(FALLBACK_MODELS)


def test_pinned_model_skips_the_chain():
    a = ScriptedAnswerer(["pinned answer"], model="gemini-3.5-flash")
    assert a.answer(system_prompt="s", user_content="u") == "pinned answer"
    assert a.attempted == ["gemini-3.5-flash"]
