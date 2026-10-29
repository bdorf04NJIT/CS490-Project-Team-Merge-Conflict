from pathlib import Path

import click
from sqlalchemy import create_engine

from .models import Base


def init_database(app):
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    engine = create_engine(app.config["DATABASE_URL"], hide_parameters=True)
    app.extensions["database"] = engine

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables; does not alter or drop existing tables."""
        Base.metadata.create_all(engine)
        click.echo("Database tables initialized.")
