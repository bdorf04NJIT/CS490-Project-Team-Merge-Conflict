from types import SimpleNamespace

import pytest

from app import create_app
from app.database import enable_row_level_security
from app.models import Base


@pytest.mark.parametrize("value", ["", " ", "invalid", "sqlite:///:memory:"])
def test_runtime_requires_postgres(value):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app({"SUPABASE_URL": "https://test.supabase.co", "DATABASE_URL": value})


def test_postgres_engine_uses_psycopg_without_connecting():
    app = create_app(
        {
            "SUPABASE_URL": "https://test.supabase.co",
            "DATABASE_URL": "postgresql+psycopg://user:password@localhost/reviewlens",
        }
    )
    engine = app.extensions["database"]
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
    engine.dispose()


class RecordingConnection:
    def __init__(self, dialect_name):
        self.dialect = SimpleNamespace(
            name=dialect_name, identifier_preparer=SimpleNamespace(quote=lambda name: f'"{name}"')
        )
        self.statements = []

    def execute(self, statement):
        self.statements.append(str(statement))


def test_row_level_security_is_enabled_on_every_app_table():
    connection = RecordingConnection("postgresql")
    enable_row_level_security(connection)
    expected = {
        f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'
        for table in Base.metadata.sorted_tables
    }
    assert set(connection.statements) == expected
    assert {"analysis_targets", "reviews", "ingestion_runs"} <= set(Base.metadata.tables)


def test_row_level_security_is_skipped_for_sqlite():
    connection = RecordingConnection("sqlite")
    enable_row_level_security(connection)
    assert connection.statements == []
