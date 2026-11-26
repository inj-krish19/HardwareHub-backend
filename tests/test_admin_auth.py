"""The admin login. Pure tests, no database."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core import admin_auth
from app.core.config import MIN_ADMIN_SECRET_LENGTH, Settings

GOOD = SimpleNamespace(ADMIN_ID="krish-admin", ADMIN_SECRET="a-long-secret-value-123")
REQUEST = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))


@pytest.fixture(autouse=True)
def fixed_settings(monkeypatch):
    monkeypatch.setattr(admin_auth, "get_settings", lambda: GOOD)


def _login(admin_id, secret, request=REQUEST):
    return admin_auth.require_admin(request, admin_id, secret)


def test_the_right_credentials_pass():
    assert _login("krish-admin", "a-long-secret-value-123") is None


@pytest.mark.parametrize(
    "admin_id,secret",
    [("krish-admin", "wrong"), ("someone", "a-long-secret-value-123"), ("", ""), ("KRISH-ADMIN", "a-long-secret-value-123"),
     ("krish-admin", "a-long-secret-value-123 "), ("krish-admin", "a-long-secret-value-12")],
)
def test_anything_else_is_401(admin_id, secret):
    with pytest.raises(HTTPException) as err:
        _login(admin_id, secret)
    assert err.value.status_code == 401 and err.value.detail == "Invalid admin credentials."


def test_a_wrong_id_and_a_wrong_secret_get_the_same_answer():
    answers = []
    for admin_id, secret in (("nope", "a-long-secret-value-123"), ("krish-admin", "nope")):
        with pytest.raises(HTTPException) as err:
            _login(admin_id, secret)
        answers.append((err.value.status_code, err.value.detail))
    assert answers[0] == answers[1]


def test_non_ascii_input_is_just_a_failed_login():
    with pytest.raises(HTTPException) as err:
        _login("krish-admin", "séc\u00fcret-€")
    assert err.value.status_code == 401


def test_both_values_are_always_compared(monkeypatch):
    calls = []
    monkeypatch.setattr(admin_auth, "_same", lambda a, b: calls.append(1) or False)
    with pytest.raises(HTTPException):
        _login("wrong-id", "wrong-secret")
    assert len(calls) == 2  # the id check failing must not skip the secret check


def test_the_comparison_is_the_constant_time_one(monkeypatch):
    # "Constant time" cannot be seen from the result, so check the right function is used.
    seen = []
    real = admin_auth.secrets.compare_digest
    monkeypatch.setattr(admin_auth.secrets, "compare_digest", lambda a, b: seen.append((a, b)) or real(a, b))
    _login("krish-admin", "a-long-secret-value-123")
    assert seen == [(b"krish-admin", b"krish-admin"), (b"a-long-secret-value-123", b"a-long-secret-value-123")]


def test_a_failed_login_is_logged_without_the_credentials(caplog):
    with caplog.at_level("WARNING", logger=admin_auth.logger.name):
        with pytest.raises(HTTPException):
            _login("krish-admin", "super-secret-guess")
    assert "203.0.113.9" in caplog.text
    assert "super-secret-guess" not in caplog.text and "a-long-secret-value-123" not in caplog.text


def test_a_failed_login_with_no_client_address_still_works(caplog):
    with pytest.raises(HTTPException):
        _login("x", "y", SimpleNamespace(client=None))


# ---- settings: the secret must be long ----

def _settings(**overrides):
    values = dict(DATABASE_URL="postgresql://u:p@h/db", CORS_ORIGIN="http://localhost:3000",
                  ADMIN_ID="krish-admin", ADMIN_SECRET="x" * MIN_ADMIN_SECRET_LENGTH)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_a_secret_of_the_minimum_length_is_accepted():
    assert _settings().ADMIN_SECRET == "x" * MIN_ADMIN_SECRET_LENGTH


def test_a_short_secret_stops_the_app_from_starting():
    with pytest.raises(ValidationError, match="at least 16 characters"):
        _settings(ADMIN_SECRET="x" * (MIN_ADMIN_SECRET_LENGTH - 1))


def test_a_blank_admin_id_is_refused():
    with pytest.raises(ValidationError, match="ADMIN_ID"):
        _settings(ADMIN_ID="   ")


# ---- every admin route is behind the login ----

def test_every_admin_route_requires_the_login(monkeypatch):
    for key, value in (("DATABASE_URL", "postgresql://u:p@localhost/none"), ("CORS_ORIGIN", "http://localhost:3000"),
                       ("ADMIN_ID", "krish-admin"), ("ADMIN_SECRET", "a-long-secret-value-123")):
        monkeypatch.setenv(key, __import__("os").environ.get(key, value))
    from app.main import app

    admin_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/api/v1/admin")]
    assert len(admin_routes) >= 10
    unprotected = [r.path for r in admin_routes if not any(d.call is admin_auth.require_admin for d in r.dependant.dependencies)]
    assert unprotected == []


def test_the_public_routes_are_not_behind_the_login():
    from app.main import app

    public = {r.path for r in app.routes if getattr(r, "path", "").startswith(("/api/v1/chat", "/api/v1/guides", "/api/v1/products", "/api/v1/categories"))}
    assert public, "expected public routes"
    for route in app.routes:
        if getattr(route, "path", "") in public:
            assert not any(d.call is admin_auth.require_admin for d in route.dependant.dependencies)