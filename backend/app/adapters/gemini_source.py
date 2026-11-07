"""Boundary to Google Gemini for Review Q&A.

This is the only place that talks to the model. The Q&A service builds the system
prompt (S2-013) and the review-bearing user turn, hands them here, and this returns
the model's raw text reply. Keeping the call isolated mirrors the review-source
boundary and lets it be swapped or disabled without touching the service.

Free-tier Gemini models flip between available and overloaded (503/504) minute to
minute, so a single model is unreliable. The adapter tries an ordered chain of
models, leading with the most consistently available, and only falls back to the
next one on a transient failure. Non-transient failures (quota, missing model, bad
request, auth) are surfaced at once, since another model would not help.
"""

# Ordered most-reliable first. The lite models have the highest free-tier headroom and
# were the least contended in testing, so they lead; the full flash model is the
# higher-quality last resort. Setting GEMINI_MODEL pins a single model and skips the chain.
FALLBACK_MODELS = (
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
)

# Cap how long one request waits on the model. Without this, an overloaded Gemini can
# leave the request hanging; a bounded deadline fails fast so we can try the next model.
REQUEST_TIMEOUT_MS = 20000

# Status codes where trying a different model is worthwhile (transient / capacity).
# Everything else (429 quota, 404 missing, 400 bad request, 401/403 auth) is not helped
# by a fallback and is surfaced immediately.
RETRYABLE_STATUSES = (503, 504)


class UnconfiguredGemini:
    """Used when no GEMINI_API_KEY is set, so the app still boots."""

    def answer(self, *, system_prompt, user_content):
        from ..errors import QaUnavailable

        raise QaUnavailable("Gemini is not configured. Set GEMINI_API_KEY in backend/.env.")


class GeminiReviewAnswerer:
    """Calls Gemini for a single-turn JSON reply, falling back across models on overload."""

    def __init__(self, api_key, *, model=None):
        if not api_key:
            raise ValueError("A Gemini API key is required.")
        self._api_key = api_key
        # An explicit model pins the request to just that one; otherwise use the chain.
        self._models = (model,) if model else FALLBACK_MODELS

    def answer(self, *, system_prompt, user_content):
        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types

        from ..errors import QaUnavailable

        client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.2,
        )

        last_exc = None
        for model in self._models:
            try:
                text = self._generate(client, model, user_content, config)
            except genai_errors.APIError as exc:
                last_exc = exc
                if getattr(exc, "code", None) in RETRYABLE_STATUSES:
                    # This model is overloaded; try the next one in the chain.
                    continue
                # Quota, missing model, bad request, or auth: another model won't help.
                raise QaUnavailable() from exc

            if text:
                return text
            # An empty reply is treated like a transient failure: try the next model.
            last_exc = None

        # Every model was overloaded or returned nothing.
        raise QaUnavailable() from last_exc

    def _generate(self, client, model, user_content, config):
        """Single model call. Isolated so the fallback logic can be tested without the SDK."""
        response = client.models.generate_content(model=model, contents=user_content, config=config)
        return response.text
