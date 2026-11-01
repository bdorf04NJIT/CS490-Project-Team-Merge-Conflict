from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.models import AnalysisTarget
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

VALUES = {
    "owner_id": "user-a",
    "name": "Joe's Coffee",
    "platform": "google_maps",
    "source_url": "https://www.google.com/maps/place/Joe's+Coffee",
}
REQUIRED = ["owner_id", "name", "platform", "source_url"]


@pytest.fixture
def engine(client):
    return client.application.extensions["database"]


def save(engine, **overrides):
    with Session(engine) as session, session.begin():
        target = AnalysisTarget(**{**VALUES, **overrides})
        session.add(target)
        session.flush()
        return target.id


def test_saved_target_is_retrieved_with_same_values_and_owner(engine):
    before = datetime.now(UTC)
    target_id = save(engine)

    with Session(engine) as session:
        stored = session.get(AnalysisTarget, target_id)

    assert stored is not None
    for field, value in VALUES.items():
        assert getattr(stored, field) == value
    created = stored.created_at.replace(tzinfo=UTC)
    assert before - timedelta(seconds=1) <= created <= datetime.now(UTC) + timedelta(seconds=1)


def test_each_target_gets_its_own_uuid(engine):
    first, second = save(engine), save(engine, owner_id="user-b")
    assert first != second
    assert str(UUID(first)) == first and str(UUID(second)) == second


def test_targets_are_retrievable_by_owner(engine):
    save(engine, name="A1")
    save(engine, name="A2")
    save(engine, owner_id="user-b", name="B1")
    with Session(engine) as session:
        names = session.scalars(
            select(AnalysisTarget.name).where(AnalysisTarget.owner_id == "user-a")
        ).all()
    assert sorted(names) == ["A1", "A2"]


@pytest.mark.parametrize("field", REQUIRED)
def test_database_rejects_target_missing_required_field(engine, field):
    with pytest.raises(IntegrityError):
        save(engine, **{field: None})
    with Session(engine) as session:
        assert session.scalars(select(AnalysisTarget)).all() == []