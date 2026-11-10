import pytest

from app.services.review_normalization import classify_review, normalize_review, normalize_reviews


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
    assert result.skip_reasons == {"missing_text": 1, "invalid_rating": 1}


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ({"review_text": "", "rating": 5}, "missing_text"),
        ({"review_text": "   ", "rating": 5}, "missing_text"),
        ({"rating": 5}, "missing_text"),
        ({"review_text": "x" * 20001, "rating": 5}, "text_too_long"),
        ({"review_text": "Good", "rating": None}, "invalid_rating"),
        ({"review_text": "Good", "rating": 6}, "invalid_rating"),
        ({"review_text": "Good", "rating": "five"}, "invalid_rating"),
        (None, "malformed_record"),
        ("review_text,rating", "malformed_record"),
    ],
)
def test_skipped_record_gets_one_reason_category(row, reason):
    assert classify_review(row) == (None, reason)


def test_skip_reason_counts_always_add_up_to_skipped_count():
    result = normalize_reviews(
        [
            {"review_text": "Fine", "rating": 4},
            {"review_text": "", "rating": None},  # missing text wins; counted once
            {"review_text": "", "rating": 3},
            {"review_text": "Bad rating", "rating": 0},
            None,
        ]
    )
    assert result.skipped_count == 4
    assert result.skip_reasons == {"missing_text": 2, "invalid_rating": 1, "malformed_record": 1}
    assert sum(result.skip_reasons.values()) == result.skipped_count


def test_clean_batch_has_no_skip_reasons():
    result = normalize_reviews([{"review_text": "Fine", "rating": 4}])
    assert (result.skipped_count, result.skip_reasons) == (0, {})


def test_extracted_snippet_fallback():
    value = normalize_review({"rating": 3, "extracted_snippet": {"original": "Detailed feedback"}})
    assert value.text == "Detailed feedback"
