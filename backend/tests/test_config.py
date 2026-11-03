import pytest

from app import create_app

DATABASE_URL = "postgresql+psycopg://user:password@localhost/reviewlens"


@pytest.mark.parametrize("value", ["", "/"])
def test_missing_supabase_url_fails_with_clear_message(monkeypatch, value):
    # An env var that is already set wins over backend/.env, so a developer's
    # real .env file cannot affect this test.
    monkeypatch.setenv("SUPABASE_URL", value)
    with pytest.raises(RuntimeError, match="Set SUPABASE_URL in backend/.env"):
        create_app({"DATABASE_URL": DATABASE_URL})


def test_invalid_database_url_error_does_not_echo_the_value():
    secret_looking = "not-a-url-with-password-hunter2"
    with pytest.raises(RuntimeError, match="DATABASE_URL") as error:
        create_app({"SUPABASE_URL": "https://test.supabase.co", "DATABASE_URL": secret_looking})
    assert secret_looking not in str(error.value)
