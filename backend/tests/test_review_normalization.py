import pytest

from app.services.review_normalization import normalize_review, normalize_reviews


def test_serpapi_review_normalization_preserves_metadata():
    result = normalize_review(
        {
            "snippet": "  The staff were helpful.  ",
            "rating": 4.5,
            "review_id": "r123",
            "iso_date": "2026-10-20T00:00:00Z",
            "user": {"name": "Sam"},
            "link": "https://www.google.com/maps/reviews/r123",
            "source": "Google",
        }
    )
    assert result.text == "The staff were helpful."
    assert result.rating == 4.5
    assert result.source_review_id == "r123"
    assert result.reviewer_name == "Sam"
    assert result.source_name == "Google"


def test_csv_review_without_optional_metadata_is_accepted():
    review = normalize_review({"review_text": "Good coffee", "rating": "5"})
    assert review.text == "Good coffee"
    assert review.reviewer_name is None


@pytest.mark.parametrize(
    "row",
    [
        {"review_text": "", "rating": 5},
        {"review_text": "", "rating": 1},
        {"review_text": "Good", "rating": None},
        {"review_text": "Good", "rating": 0},
        {"review_text": "Good", "rating": 6},
        {"review_text": "Good", "rating": "NaN"},
        {"review_text": "Good", "rating": True},
        {"review_text": "x" * 20001, "rating": 5},
        None,
    ],
)
def test_bad_review_is_rejected(row):
    assert normalize_review(row) is None


def test_partial_import_skips_only_bad_rows():
    result = normalize_reviews(
        [
            {"snippet": "Great", "rating": 5},
            {"snippet": "", "rating": 4},
            {"snippet": "Noisy", "rating": 2},
            {"snippet": "Expensive", "rating": "bad"},
        ]
    )
    assert result.total_count == 4
    assert result.skipped_count == 2
    assert [r.text for r in result.reviews] == ["Great", "Noisy"]


def test_extracted_snippet_fallback():
    value = normalize_review({"rating": 3, "extracted_snippet": {"original": "Detailed feedback"}})
    assert value.text == "Detailed feedback"
