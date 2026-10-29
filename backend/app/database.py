import click
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .models import Base


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
        """Create missing tables; does not alter or drop existing tables."""
        Base.metadata.create_all(engine)
        click.echo("Database tables initialized.")
