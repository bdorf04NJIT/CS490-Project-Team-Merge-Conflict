"""Review summary computed only from the persisted, owner-scoped review dataset.

The summary and Q&A must describe the same reviews, so both read the dataset through
``active_reviews``. Nothing here uses source data, browser state, or model output.
"""

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AnalysisTarget, Review
from .review_storage import latest_run
from .targets import find_owned_target

STAR_VALUES = (1, 2, 3, 4, 5)


def active_reviews(*, owner_id, target_id):
    """Select the active review dataset for one owned target.

    Every persisted review for the target belongs to the dataset. Records skipped
    during ingestion were never stored, and failed runs store no reviews, so neither
    can be counted. Ownership is part of the query itself, so another user's target
    yields no rows even if a caller forgets its own ownership check.
    """
    return (
        select(Review)
        .join(AnalysisTarget, AnalysisTarget.id == Review.target_id)
        .where(Review.target_id == target_id, AnalysisTarget.owner_id == owner_id)
    )


def summarize_reviews(engine, *, owner_id, target_id):
    """Return review count, average rating, and star distribution for an owned target."""
    with Session(engine) as session:
        # Raise NotFound (404) for a missing or foreign target instead of an empty summary.
        find_owned_target(session, owner_id=owner_id, target_id=target_id)
        dataset = active_reviews(owner_id=owner_id, target_id=target_id).subquery()
        count, average = session.execute(
            select(func.count(dataset.c.id), func.avg(dataset.c.rating))
        ).one()
        rating_counts = session.execute(
            select(dataset.c.rating, func.count()).group_by(dataset.c.rating)
        ).all()

    distribution = {str(star): 0 for star in STAR_VALUES}
    for rating, rating_count in rating_counts:
        # Fractional ratings (e.g. 4.5) count toward the whole star they reached.
        distribution[str(math.floor(rating))] += rating_count

    return {
        "target_id": target_id,
        "review_count": count,
        "average_rating": round(average, 2) if count else None,
        "rating_distribution": distribution,
        "latest_ingestion": latest_run(engine, owner_id=owner_id, target_id=target_id),
    }
