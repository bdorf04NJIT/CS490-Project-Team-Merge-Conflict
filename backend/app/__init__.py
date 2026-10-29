import os
from dotenv import load_dotenv
from flask import Flask
from .errors import register_error_handlers
from .routes import bp


def create_app(config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config["JWT_SECRET"] = os.environ.get("SUPABASE_JWT_SECRET", "")
    if config:
        app.config.update(config)
    register_error_handlers(app)
    app.register_blueprint(bp)
    return app
