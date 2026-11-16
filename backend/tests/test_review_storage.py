import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import AnalysisTarget, Base, IngestionRun, Review
from app.services.review_storage import latest_run, list_reviews, persist_reviews, record_failed_run


@pytest.fixture
def storage():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                AnalysisTarget(
                    id="a",
                    owner_id="user-a",
                    name="A",
                    platform="google_maps",
                    source_url="https://www.google.com/maps/place/A",
                ),
                AnalysisTarget(
                    id="b",
                    owner_id="user-b",
                    name="B",
                    platform="google_maps",
                    source_url="https://www.google.com/maps/place/B",
                ),
            ]
        )
    yield engine
    engine.dispose()


def test_persists_reviews_and_run_for_correct_owner(storage):
    run = persist_reviews(
        storage,
        owner_id="user-a",
        target_id="a",
        source_kind="google_maps_csv",
        reviews=[{"text": "Great", "rating": 5.0}, {"text": "Okay", "rating": 3.0}],
        skipped_count=1,
    )
    assert run["status"] == "partial"
    assert (run["total_count"], run["imported_count"], run["skipped_count"]) == (3, 2, 1)
    assert sorted(r["text"] for r in list_reviews(storage, owner_id="user-a", target_id="a")) == [
        "Great",
        "Okay",
    ]
    assert latest_run(storage, owner_id="user-a", target_id="a")["status"] == "partial"


def test_failed_ingestion_records_no_fabricated_reviews(storage):
    run = record_failed_run(
        storage,
        owner_id="user-a",
        target_id="a",
        source_kind="serpapi_google_maps",
        message="Provider failed",
    )
    assert run["status"] == "failed"
    assert run["skip_reasons"] == {}
    assert list_reviews(storage, owner_id="user-a", target_id="a") == []


def test_skip_reasons_are_persisted_with_the_run(storage):
    run = persist_reviews(
        storage,
        owner_id="user-a",
        target_id="a",
        source_kind="google_maps_csv",
        reviews=[{"text": "Great", "rating": 5.0}],
        skipped_count=3,
        skip_reasons={"missing_text": 2, "invalid_rating": 1},
    )
    assert run["skip_reasons"] == {"invalid_rating": 1, "missing_text": 2}
    stored = latest_run(storage, owner_id="user-a", target_id="a")
    assert (stored["status"], stored["skipped_count"]) == ("partial", 3)
    assert stored["skip_reasons"] == {"invalid_rating": 1, "missing_text": 2}


def test_failed_run_keeps_counts_of_rejected_records(storage):
    run = record_failed_run(
        storage,
        owner_id="user-a",
        target_id="a",
        source_kind="google_maps_csv",
        message="No usable written reviews with ratings from 1 to 5 were found.",
        total_count=2,
        skipped_count=2,
        skip_reasons={"invalid_rating": 2},
    )
    assert run["skip_reasons"] == {"invalid_rating": 2}
    stored = latest_run(storage, owner_id="user-a", target_id="a")
    assert (stored["total_count"], stored["imported_count"], stored["skipped_count"]) == (2, 0, 2)
    assert stored["skip_reasons"] == {"invalid_rating": 2}


def test_cross_user_read_and_write_does_not_leak_or_mutate(storage):
    run = persist_reviews(
        storage,
        owner_id="user-a",
        target_id="a",
        source_kind="google_maps_csv",
        reviews=[{"text": "Private review", "rating": 5.0}],
        skipped_count=0,
    )
    with pytest.raises(NotFound):
        list_reviews(storage, owner_id="user-b", target_id="a")
    with pytest.raises(NotFound):
        latest_run(storage, owner_id="user-b", target_id="a")
    with pytest.raises(NotFound):
        persist_reviews(
            storage,
            owner_id="user-b",
            target_id="a",
            source_kind="google_maps_csv",
            reviews=[{"text": "Bad", "rating": 1.0}],
            skipped_count=0,
        )
    with pytest.raises(NotFound):
        record_failed_run(
            storage, owner_id="user-b", target_id="a", source_kind="google_maps_csv", message="Bad"
        )
    with Session(storage) as session:
        assert len(session.scalars(select(Review)).all()) == 1
        assert len(session.scalars(select(IngestionRun)).all()) == 1
    assert latest_run(storage, owner_id="user-a", target_id="a")["id"] == run["id"]


def test_database_rejects_invalid_rating(storage):
    with pytest.raises(IntegrityError):
        persist_reviews(
            storage,
            owner_id="user-a",
            target_id="a",
            source_kind="google_maps_csv",
            reviews=[{"text": "Good", "rating": 7.0}],
            skipped_count=0,
        )
    with Session(storage) as session:
        assert session.scalars(select(IngestionRun)).all() == []
