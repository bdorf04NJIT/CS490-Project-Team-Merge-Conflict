def test_authenticated_request_succeeds(client, auth_header):
    res = client.get("/api/me", headers=auth_header("user-a"))
    assert res.status_code == 200
    assert res.get_json() == {"user_id": "user-a"}


def test_missing_token_returns_401(client):
    res = client.get("/api/me")
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_bad_signature_returns_401(client, auth_header):
    res = client.get("/api/me", headers=auth_header(secret="this_is_the_WRONG_secret_blahblahblahblah!"))
    assert res.status_code == 401


def test_expired_token_returns_401(client, auth_header):
    res = client.get("/api/me", headers=auth_header(expires_in=-10))
    assert res.status_code == 401


def test_401_does_not_leak_protected_data(client):
    body = client.get("/api/me").get_data(as_text=True)
    assert "user_id" not in body
    assert "user-a" not in body


def test_health_is_public(client):
    assert client.get("/api/health").status_code == 200


def test_required_claims_and_bearer_scheme(client, auth_header):
    import jwt
    from conftest import SECRET

    original = auth_header()["Authorization"].split()[1]
    claims = jwt.decode(original, options={"verify_signature": False})
    for field in ("sub", "exp", "iss", "aud"):
        invalid = dict(claims)
        del invalid[field]
        token = jwt.encode(invalid, SECRET, algorithm="HS256")
        assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    for field, value in (("iss", "https://other.supabase.co/auth/v1"), ("aud", "other"), ("sub", "")):
        invalid = {**claims, field: value}
        token = jwt.encode(invalid, SECRET, algorithm="HS256")
        assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/me", headers={"Authorization": original}).status_code == 401


def test_provider_public_key_verification(monkeypatch):
    import time
    from types import SimpleNamespace

    import jwt
    from app import create_app
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    app = create_app({"SUPABASE_URL": "https://test.supabase.co", "JWT_SECRET": ""})
    monkeypatch.setattr(app.extensions["supabase_jwks"], "get_signing_key_from_jwt",
                        lambda token: SimpleNamespace(key=key.public_key()))
    claims = {"sub": "provider-user", "iss": "https://test.supabase.co/auth/v1",
              "aud": "authenticated", "exp": int(time.time()) + 60}
    token = jwt.encode(claims, key, algorithm="ES256")
    client = app.test_client()
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.get_json() == {"user_id": "provider-user"}
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(claims, wrong_key, algorithm="ES256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
