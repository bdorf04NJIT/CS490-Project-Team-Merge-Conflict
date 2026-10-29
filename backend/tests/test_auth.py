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
