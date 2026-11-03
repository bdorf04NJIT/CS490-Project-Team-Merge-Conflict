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
    # Team-authorized credentials only; multi-key config overrides legacy single-key config.
    keys_env = os.environ.get("SERPAPI_API_KEYS", "").strip()
    keys = [part.strip() for part in keys_env.split(",") if part.strip()] if keys_env else []
    if not keys and os.environ.get("SERPAPI_API_KEY", "").strip():
        keys = [os.environ["SERPAPI_API_KEY"].strip()]
    try:
        max_pages = int(os.environ.get("SERPAPI_MAX_PAGES", "3"))
    except ValueError:
        raise RuntimeError("SERPAPI_MAX_PAGES must be an integer between 1 and 10") from None
    if not 1 <= max_pages <= 10:
        raise RuntimeError("SERPAPI_MAX_PAGES must be between 1 and 10")
    app.extensions.setdefault(
        "review_source",
        SerpApiGoogleMapsSource(keys, max_pages=max_pages, quota_preflight=True)
        if keys
        else UnconfiguredReviewSource(),
    )
    app.register_blueprint(bp)
    return app
