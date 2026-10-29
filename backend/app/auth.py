from functools import wraps

import jwt
from flask import current_app, g, request

from .adapters.supabase_auth import verify_token
from .errors import Unauthenticated


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        parts = request.headers.get("Authorization", "").split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise Unauthenticated()
        try:
            claims = verify_token(
                parts[1], current_app.config["JWT_ISSUER"],
                current_app.extensions.get("supabase_jwks"),
                current_app.config["JWT_SECRET"],
            )
        except jwt.PyJWTError:
            raise Unauthenticated() from None
        g.user_id = claims["sub"]
        return fn(*args, **kwargs)

    return wrapper
