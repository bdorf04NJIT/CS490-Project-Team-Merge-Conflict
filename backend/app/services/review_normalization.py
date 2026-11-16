"""Canonical Review representation shared by the ingestion and persistence layers."""

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MAX_REVIEW_LENGTH = 20000

# User-facing reason categories for records that were not added to the dataset.
# Raw parser diagnostics are deliberately not exposed; each skipped record gets
# exactly one category, so the per-reason counts always add up to skipped_count.
MISSING_TEXT = "missing_text"
TEXT_TOO_LONG = "text_too_long"
INVALID_RATING = "invalid_rating"
MALFORMED_RECORD = "malformed_record"
SKIP_REASONS = (MISSING_TEXT, TEXT_TOO_LONG, INVALID_RATING, MALFORMED_RECORD)


@dataclass(frozen=True)
class NormalizedReview:
    text: str
    rating: float
    source_review_id: str | None = None
    reviewer_name: str | None = None
    review_date: str | None = None
    review_url: str | None = None
    source_name: str | None = None


@dataclass(frozen=True)
class NormalizationResult:
    reviews: list[NormalizedReview]
    total_count: int
    skipped_count: int
    skip_reasons: dict[str, int] = field(default_factory=dict)


def _first(row, names):
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return None


def _optional(value, limit):
    if isinstance(value, str):
        value = value.strip()
        return value[:limit] or None
    return None


def _rating(value):
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        if number.is_finite() and 1 <= number <= 5:
            return float(number)
    except (InvalidOperation, TypeError, ValueError):
        pass
    return None


def classify_review(row):
    """Return (review, None) for a usable record, or (None, reason) when it is skipped."""
    if not isinstance(row, dict):
        return None, MALFORMED_RECORD
    text = _first(row, ("review_text", "text", "review", "snippet", "content"))
    if not text and isinstance(row.get("extracted_snippet"), dict):
        text = row["extracted_snippet"].get("original")
    if not isinstance(text, str) or not text.strip():
        return None, MISSING_TEXT
    if len(text.strip()) > MAX_REVIEW_LENGTH:
        return None, TEXT_TOO_LONG
    rating = _rating(_first(row, ("rating", "stars", "review_rating")))
    if rating is None:
        return None, INVALID_RATING
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    review = NormalizedReview(
        text=text.strip(),
        rating=rating,
        source_review_id=_optional(_first(row, ("review_id", "source_review_id", "id")), 255),
        reviewer_name=_optional(
            _first(row, ("reviewer_name", "reviewer", "author")) or user.get("name"), 255
        ),
        review_date=_optional(_first(row, ("iso_date", "review_date", "date")), 100),
        review_url=_optional(_first(row, ("review_url", "link", "url")), 2048),
        source_name=_optional(_first(row, ("source", "source_name")), 100),
    )
    return review, None


def normalize_review(row):
    return classify_review(row)[0]


def normalize_reviews(rows):
    """Skip malformed individual records, without losing good neighbors."""
    if not isinstance(rows, list):
        raise ValueError("Review source returned an invalid review collection")
    normalized = []
    reasons = Counter()
    for row in rows:
        candidate, reason = classify_review(row)
        if candidate is not None:
            normalized.append(candidate)
        else:
            reasons[reason] += 1
    return NormalizationResult(
        reviews=normalized,
        total_count=len(rows),
        skipped_count=len(rows) - len(normalized),
        skip_reasons=dict(reasons),
    )
