"""Shared test setup.

Most tests here are pure (no database). The API tests need a real PostgreSQL
database. They only run when TEST_DATABASE_URL is set, and they WIPE the guide
and catalog tables first, so the database name must contain "test"; this file
refuses anything else, to protect your real data.

Windows PowerShell, from backend/ (create the empty database once first):
    $env:TEST_DATABASE_URL = "postgresql://postgres:password@localhost:5432/hardware_hub_test"
    python -m pytest
"""
import os

import pytest
from sqlalchemy.engine import make_url

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

if TEST_DB_URL:
    db_name = make_url(TEST_DB_URL).database or ""
    if "test" not in db_name.lower():
        raise RuntimeError(
            f"TEST_DATABASE_URL points at database {db_name!r}. The API tests delete data, "
            "so the database name must contain 'test'. Refusing to run."
        )
    # Settings are read from the environment first, then backend/.env.
    os.environ["DATABASE_URL"] = TEST_DB_URL
    os.environ.setdefault("CORS_ORIGIN", "http://localhost:3000")
    os.environ.setdefault("ADMIN_ID", "test-admin")
    os.environ.setdefault("ADMIN_SECRET", "test-secret")

def pytest_report_header(config):
    """Shown at the top of every run, so you can see which database the API tests will use."""
    if not TEST_DB_URL:
        return "API tests: SKIPPED (TEST_DATABASE_URL is not set)"
    url = make_url(TEST_DB_URL)
    return f"API tests: database {url.database!r} on {url.host or 'local socket'}:{url.port or 5432} as user {url.username!r}"


WIPE = "TRUNCATE guide_feedback, diagnosis_rule, symptom, product_link, blog_post, product, category CASCADE"


@pytest.fixture(scope="session")
def client():
    if not TEST_DB_URL:
        pytest.skip("set TEST_DATABASE_URL (a database whose name contains 'test') to run the API tests")
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    from app.db.session import engine
    from app.db.sync_schema import sync_schema
    from app.main import app

    # Fail once, with a readable message, instead of the same long error in every test.
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        url = make_url(TEST_DB_URL)
        pytest.fail(
            f"Cannot connect to the test database {url.database!r} on {url.host}:{url.port or 5432} "
            f"as {url.username!r}. Create the empty database first and check the user and password in "
            f"TEST_DATABASE_URL.\nDriver said: {str(exc.orig).strip()}",
            pytrace=False,
        )
    sync_schema()
    return TestClient(app)


@pytest.fixture()
def clean_db(client):
    from sqlalchemy import text

    from app.db.session import engine

    with engine.begin() as conn:
        conn.execute(text(WIPE))
    yield


@pytest.fixture()
def admin_headers(client):
    from app.core.config import get_settings

    settings = get_settings()
    return {"X-Admin-Id": settings.ADMIN_ID, "X-Admin-Secret": settings.ADMIN_SECRET}