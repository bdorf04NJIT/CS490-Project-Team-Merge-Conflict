"""Atomic persistence and tenant-isolated reads for imported customer reviews."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import NotFound
from ..models import AnalysisTarget, IngestionRun, IngestionRunSkipReason, Review


def _owned_target(session, *, target_id, owner_id):
    target = session.scalar(
        select(AnalysisTarget).where(
            AnalysisTarget.id == target_id, AnalysisTarget.owner_id == owner_id
        )
    )
    if target is None:
        raise NotFound("We couldn't find that analysis target.")
    return target


def _run_output(run):
    return {
        "id": run.id,
        "target_id": run.target_id,
        "source_kind": run.source_kind,
        "status": run.status,
        "total_count": run.total_count,
        "imported_count": run.imported_count,
        "skipped_count": run.skipped_count,
        "skip_reasons": {item.reason: item.count for item in run.skip_reasons},
        "message": run.message,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat(),
    }


def _reason_rows(skip_reasons):
    return [
        IngestionRunSkipReason(reason=reason, count=count)
        for reason, count in sorted((skip_reasons or {}).items())
        if count > 0
    ]


def persist_reviews(
    engine, *, owner_id, target_id, reviews, skipped_count, source_kind, skip_reasons=None
):
    """Commit run and normalized reviews as one transaction; never replace old reviews."""
    if not reviews:
        raise ValueError("No valid reviews to persist")
    with Session(engine) as session, session.begin():
        _owned_target(session, target_id=target_id, owner_id=owner_id)
        # Re-ingesting a target must not save the same provider review twice.
        seen = set(
            session.scalars(
                select(Review.source_review_id).where(
                    Review.target_id == target_id, Review.source_review_id.is_not(None)
                )
            )
        )
        new_reviews = []
        for review in reviews:
            review_id = review.get("source_review_id")
            if review_id is not None:
                if review_id in seen:
                    continue
                seen.add(review_id)
            new_reviews.append(review)
        already_saved = len(reviews) - len(new_reviews)
        if skipped_count:
            message = "Import completed with skipped reviews."
        elif already_saved:
            message = f"Import succeeded. {already_saved} reviews were already saved."
        else:
            message = "Import succeeded."
        run = IngestionRun(
            target_id=target_id,
            source_kind=source_kind,
            status="partial" if skipped_count else "succeeded",
            total_count=len(reviews) + skipped_count,
            imported_count=len(new_reviews),
            skipped_count=skipped_count,
            message=message,
            skip_reasons=_reason_rows(skip_reasons),
        )
        session.add(run)
        session.flush()
        for review in new_reviews:
            session.add(Review(target_id=target_id, ingestion_run_id=run.id, **review))
        session.flush()
        return _run_output(run)


def record_failed_run(
    engine,
    *,
    owner_id,
    target_id,
    source_kind,
    message,
    total_count=0,
    skipped_count=0,
    skip_reasons=None,
):
    """Record a run that added no reviews; rejected records still keep their counts."""
    with Session(engine) as session, session.begin():
        _owned_target(session, target_id=target_id, owner_id=owner_id)
        run = IngestionRun(
            target_id=target_id,
            source_kind=source_kind,
            status="failed",
            total_count=total_count,
            imported_count=0,
            skipped_count=skipped_count,
            message=message[:500],
            skip_reasons=_reason_rows(skip_reasons),
        )
        session.add(run)
        session.flush()
        return _run_output(run)


def latest_run(engine, *, owner_id, target_id):
    with Session(engine) as session:
        _owned_target(session, target_id=target_id, owner_id=owner_id)
        run = session.scalar(
            select(IngestionRun)
            .where(IngestionRun.target_id == target_id)
            .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
            .limit(1)
        )
        return _run_output(run) if run else None


def list_reviews(engine, *, owner_id, target_id, offset=0):
    """Return at most 100 reviews; an unfamiliar target returns only NotFound."""
    with Session(engine) as session:
        _owned_target(session, target_id=target_id, owner_id=owner_id)
        rows = session.scalars(
            select(Review)
            .where(Review.target_id == target_id)
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(100)
        ).all()
        return [
            {
                "id": row.id,
                "text": row.text,
                "rating": row.rating,
                "source_review_id": row.source_review_id,
                "reviewer_name": row.reviewer_name,
                "review_date": row.review_date,
                "review_url": row.review_url,
                "source_name": row.source_name,
            }
            for row in rows
        ]
