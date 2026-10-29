import time
import jwt
import pytest
from app import create_app

SECRET = "test-secret-at-least-32-bytes-long!!"


@pytest.fixture
def client():
    return create_app({"JWT_SECRET": SECRET, "SUPABASE_URL": "https://test.supabase.co"}).test_client()


@pytest.fixture
def auth_header():
    """Build an Authorization header for any fake user (reuse for S1-012/013)."""

    def _make(user_id="user-a", secret=SECRET, expires_in=3600):
        token = jwt.encode(
            {
                "sub": user_id,
                "aud": "authenticated",
                "iss": "https://test.supabase.co/auth/v1",
                "exp": int(time.time()) + expires_in,
            },
            secret,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    return _make
