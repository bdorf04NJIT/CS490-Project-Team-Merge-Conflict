"""S3-003: Save As creates a separate analysis from the current one.

The copy gets a new identity, begins with the source's current persisted review
dataset, and is independent of the source afterwards.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound, ValidationError
from app.models import AnalysisTarget, IngestionRun, Review
from app.services.review_storage import persist_reviews
from app.services.targets import save_as_target

OWNER = "user-a"
SOURCE = {
    "owner_id": OWNER,
    "name": "Joe's Coffee",
    "platform": "google_maps",
    "source_url": "https://www.google.com/maps/place/Joe's+Coffee",
}


@pytest.fixture
def engine(client):
    return client.application.extensions["database"]


def make_source_with_reviews(engine, reviews):
    with Session(engine) as session, session.begin():
        target = AnalysisTarget(**SOURCE)
        session.add(target)
        session.flush()
        target_id = target.id
    persist_reviews(
        engine,
        owner_id=OWNER,
        target_id=target_id,
        reviews=reviews,
        skipped_count=0,
        source_kind="google_maps",
    )
    return target_id


TWO_REVIEWS = [
    {"text": "Great coffee", "rating": 5.0, "source_review_id": "r1"},
    {"text": "Too slow", "rating": 2.0, "source_review_id": "r2"},
]


def test_save_as_creates_a_new_identity_with_the_new_name(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)

    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Joe's (backup)")

    assert copy["id"] != source_id
    assert copy["name"] == "Joe's (backup)"
    assert copy["source_url"] == SOURCE["source_url"]
    assert copy["platform"] == SOURCE["platform"]


def test_copy_begins_with_the_sources_current_review_dataset(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)

    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Backup")

    with Session(engine) as session:
        copied = session.scalars(select(Review).where(Review.target_id == copy["id"])).all()
    assert sorted(r.text for r in copied) == ["Great coffee", "Too slow"]
    assert sorted(r.rating for r in copied) == [2.0, 5.0]


def test_copied_reviews_are_independent_rows_not_shared_with_the_source(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Backup")

    with Session(engine) as session:
        source_ids = set(session.scalars(select(Review.id).where(Review.target_id == source_id)))
        copy_ids = set(session.scalars(select(Review.id).where(Review.target_id == copy["id"])))
    assert source_ids and copy_ids
    assert source_ids.isdisjoint(copy_ids)


def test_deleting_the_copy_does_not_delete_the_original(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Backup")

    with Session(engine) as session, session.begin():
        session.delete(session.get(AnalysisTarget, copy["id"]))

    with Session(engine) as session:
        assert session.get(AnalysisTarget, source_id) is not None
        remaining = session.scalars(select(Review.text).where(Review.target_id == source_id)).all()
    assert sorted(remaining) == ["Great coffee", "Too slow"]


def test_renaming_the_copy_does_not_rename_the_original(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Backup")

    with Session(engine) as session, session.begin():
        session.get(AnalysisTarget, copy["id"]).name = "Renamed copy"

    with Session(engine) as session:
        assert session.get(AnalysisTarget, source_id).name == "Joe's Coffee"


def test_copy_has_an_ingestion_run_so_its_summary_and_reviews_are_coherent(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Backup")

    with Session(engine) as session:
        runs = session.scalars(
            select(IngestionRun).where(IngestionRun.target_id == copy["id"])
        ).all()
        copied = session.scalars(select(Review).where(Review.target_id == copy["id"])).all()
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    # Every copied review is anchored to the copy's own run, not the source's.
    assert {r.ingestion_run_id for r in copied} == {runs[0].id}


def test_save_as_rejects_an_empty_name(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    with pytest.raises(ValidationError):
        save_as_target(engine, owner_id=OWNER, target_id=source_id, name="   ")


def test_non_owner_cannot_save_as_another_users_analysis(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    with pytest.raises(NotFound):
        save_as_target(engine, owner_id="user-b", target_id=source_id, name="Stolen")


def test_copy_belongs_to_the_requesting_owner(engine):
    source_id = make_source_with_reviews(engine, TWO_REVIEWS)
    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Backup")
    with Session(engine) as session:
        assert session.get(AnalysisTarget, copy["id"]).owner_id == OWNER


def test_save_as_works_when_the_source_has_no_reviews(engine):
    with Session(engine) as session, session.begin():
        target = AnalysisTarget(**SOURCE)
        session.add(target)
        session.flush()
        source_id = target.id

    copy = save_as_target(engine, owner_id=OWNER, target_id=source_id, name="Empty copy")

    assert copy["id"] != source_id
    with Session(engine) as session:
        assert session.scalars(select(Review).where(Review.target_id == copy["id"])).all() == []
