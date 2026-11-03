import os
from pathlib import Path

import jwt
from dotenv import load_dotenv
from flask import Flask

from .adapters.review_source import UnconfiguredReviewSource
from .adapters.serpapi_source import SerpApiGoogleMapsSource
from .database import init_database
from .errors import register_error_handlers
from .routes import bp


def create_app(config=None):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    app = Flask(__name__)
    app.config["JWT_SECRET"] = os.environ.get("SUPABASE_JWT_SECRET", "")
    app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL", "").rstrip("/")
    app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
    if config:
        app.config.update(config)
    app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
    url = app.config["SUPABASE_URL"]
    if not url:
        raise RuntimeError("Set SUPABASE_URL in backend/.env")
    app.config["JWT_ISSUER"] = f"{url}/auth/v1"
    app.extensions["supabase_jwks"] = jwt.PyJWKClient(
        f"{url}/auth/v1/.well-known/jwks.json", timeout=5
    )
    register_error_handlers(app)
    init_database(app)
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    app.extensions.setdefault(
        "review_source", SerpApiGoogleMapsSource(key) if key else UnconfiguredReviewSource()
    )
    app.register_blueprint(bp)
    return app
