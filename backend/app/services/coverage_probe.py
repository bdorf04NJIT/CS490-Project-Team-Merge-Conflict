"""DO NOT MERGE. Deliberately untested code to prove the coverage gate fails."""


def classify_rating(rating: float) -> str:
    if rating >= 4.5:
        return "excellent"
    if rating >= 3.5:
        return "good"
    if rating >= 2.5:
        return "mixed"
    return "poor"


def average_length(texts: list[str]) -> float:
    if not texts:
        return 0.0
    total = 0
    for text in texts:
        total += len(text.strip())
    return total / len(texts)


def bucket_reviews(ratings: list[float]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for rating in ratings:
        label = classify_rating(rating)
        buckets[label] = buckets.get(label, 0) + 1
    return buckets
