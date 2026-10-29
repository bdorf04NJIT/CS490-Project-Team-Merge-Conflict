from functools import wraps

import jwt
from flask import current_app, g, request

from .errors import Unauthenticated


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        secret = current_app.config["JWT_SECRET"]
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not secret or not token:
            raise Unauthenticated()
        try:
            claims = jwt.decode(
                token, secret, algorithms=["HS256"], audience="authenticated"
            )
        except jwt.PyJWTError:
            raise Unauthenticated()
        g.user_id = claims["sub"]
        return fn(*args, **kwargs)

    return wrapper
