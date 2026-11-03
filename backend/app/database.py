import click
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .models import Base


def enable_row_level_security(connection):
    """Block Supabase Data API access to app tables; Flask connects as owner and is unaffected."""
    if connection.dialect.name != "postgresql":
        return
    quote = connection.dialect.identifier_preparer.quote
    for table in Base.metadata.sorted_tables:
        connection.execute(text(f"ALTER TABLE {quote(table.name)} ENABLE ROW LEVEL SECURITY"))


def init_database(app):
    value = app.config["DATABASE_URL"]
    if not value or not value.strip():
        raise RuntimeError("Set DATABASE_URL in backend/.env to your Postgres connection string")
    try:
        url = make_url(value)
    except ArgumentError:
        raise RuntimeError("DATABASE_URL must be a valid Postgres connection string") from None
    if url.drivername != "postgresql+psycopg" and not (
        app.testing and url.get_backend_name() == "sqlite"
    ):
        raise RuntimeError("DATABASE_URL must use postgresql+psycopg://")
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)
    app.extensions["database"] = engine

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables and enable RLS; does not drop or change columns."""
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            enable_row_level_security(connection)
        click.echo("Database tables initialized.")
