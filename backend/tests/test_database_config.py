import pytest
from app import create_app


@pytest.mark.parametrize("value", ["", " ", "invalid", "sqlite:///:memory:"])
def test_runtime_requires_postgres(value):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app({"SUPABASE_URL": "https://test.supabase.co", "DATABASE_URL": value})


def test_postgres_engine_uses_psycopg_without_connecting():
    app = create_app({
        "SUPABASE_URL": "https://test.supabase.co",
        "DATABASE_URL": "postgresql+psycopg://user:password@localhost/reviewlens",
    })
    engine = app.extensions["database"]
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
    engine.dispose()
