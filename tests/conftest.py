"""Shared test setup.

Most tests here are pure (no database). The API tests use a real PostgreSQL,
and they are written to be SAFE ON A DATABASE WITH REAL DATA (a hosted one
that has no separate test copy):

  * Every test runs inside one database transaction that is ALWAYS rolled back.
    Whatever the app or the test writes is visible only inside that
    transaction, and it is gone when the test ends. Nothing is ever committed.
  * There is no TRUNCATE and no DELETE, and the tests never change the
    schema: they only check that it is up to date (run
    `python -m app.db.sync_schema` yourself if they tell you it is not).
  * Everything a test creates carries a random name ("ztest...") so it can
    never collide with, or be mistaken for, real guides or messages. The tests
    only look at their own rows.
  * A tripwire fails the test run if anything tries to COMMIT the transaction,
    and when the run finishes it checks, on a fresh connection, that no
    "ztest" data was left behind.

The API tests only run when TEST_DATABASE_URL is set, either as an environment
variable or as a line in backend/.env. It may be the same database the app
uses. Without it they are skipped and your database is never contacted.

    TEST_DATABASE_URL = postgresql://user:password@host/dbname

The database user must be allowed to write (the writes are rolled back, but
they are real writes while the test runs). On a read-only database or a replica
the API tests are skipped with a message. Run from backend/:  python -m pytest
"""
import os
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or dotenv_values(
    Path(__file__).resolve().parent.parent / ".env"
).get("TEST_DATABASE_URL")

if TEST_DB_URL:
    # Settings are read from the environment first, then backend/.env.
    os.environ["DATABASE_URL"] = TEST_DB_URL
    os.environ.setdefault("CORS_ORIGIN", "http://localhost:3000")
    os.environ.setdefault("ADMIN_ID", "test-admin")
    os.environ.setdefault("ADMIN_SECRET", "test-secret")

# Prefixes of the random names tests give to what they create.
GUIDE_PREFIX = "ztest"  # guide titles, slugs and categories
MESSAGE_PREFIX = "zqtest"  # chat messages


def pytest_report_header(config):
    """Shown at the top of every run, so you can see which database the API tests will use."""
    if not TEST_DB_URL:
        return "API tests: SKIPPED (no TEST_DATABASE_URL in the environment or in backend/.env)"
    url = make_url(TEST_DB_URL)
    return (
        f"API tests: database {url.database!r} on {url.host or 'local socket'}:{url.port or 5432} "
        f"as {url.username!r}; every change is rolled back, nothing is kept"
    )


def _check_schema_is_current() -> None:
    """Read-only: fail with a clear message if a table or column is missing."""
    from sqlalchemy import inspect

    import app.models  # noqa: F401  (registers every model)
    from app.db.base import Base
    from app.db.session import engine

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            missing.append(f"table {table.name}")
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        missing += [f"column {table.name}.{c.name}" for c in table.columns if c.name not in have]
    if missing:
        pytest.fail(
            "The database is behind the code (missing: " + ", ".join(missing) + "). "
            "The tests never change the schema. Run  python -m app.db.sync_schema  first, then run them again.",
            pytrace=False,
        )


def _leftovers() -> int:
    """Count rows that look like test data, on a fresh connection that sees only committed data."""
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        return sum(
            conn.execute(text(sql), {"p": f"{prefix}%"}).scalar() or 0
            for sql, prefix in (
                ("SELECT count(*) FROM symptom WHERE title LIKE :p OR category LIKE :p", GUIDE_PREFIX),
                ("SELECT count(*) FROM unmatched_query WHERE text LIKE :p", MESSAGE_PREFIX),
            )
        )


@pytest.fixture(scope="session")
def client():
    if not TEST_DB_URL:
        pytest.skip("set TEST_DATABASE_URL in backend/.env to run the API tests")
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    from app.db.session import engine
    from app.main import app

    # Fail once, with a readable message, instead of the same long error in every test.
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        url = make_url(TEST_DB_URL)
        pytest.fail(
            f"Cannot connect to the test database {url.database!r} on {url.host}:{url.port or 5432} "
            f"as {url.username!r}. Check TEST_DATABASE_URL.\nDriver said: {str(exc.orig).strip()}",
            pytrace=False,
        )
    # A read-only database or a replica cannot take even the temporary writes (they are
    # rolled back, but they are still writes while a test runs). Skip, do not fail.
    with engine.connect() as conn:
        from sqlalchemy import text

        read_only = conn.execute(text("SHOW transaction_read_only")).scalar() == "on"
        replica = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar())
    if read_only or replica:
        pytest.skip(
            "the database is read-only (or a replica), so the API tests cannot run: they need to write, "
            "inside a transaction that is rolled back. Point TEST_DATABASE_URL at a writable database."
        )
    _check_schema_is_current()
    yield TestClient(app)
    left = _leftovers()
    assert left == 0, f"{left} test row(s) were left in the database. A test committed data. This must not happen."


@pytest.fixture()
def db(client):
    """A session whose every change is rolled back when the test ends.

    The app's own database dependency is replaced with this session, so requests
    made through `client` write into the same transaction. The app's commit() calls
    only release a savepoint inside it. A real COMMIT is blocked.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.db.session import engine, get_db
    from app.main import app

    connection = engine.connect()
    outer = connection.begin()

    def forbid_commit(_conn):
        raise RuntimeError("A test tried to COMMIT. API tests must never keep any data.")

    event.listen(connection, "commit", forbid_commit)
    session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        was_open = outer.is_active
        outer.rollback()  # discards everything the test wrote
        connection.close()
        assert was_open, "the test's transaction ended early, so its data may not have been rolled back"


@pytest.fixture()
def tag() -> str:
    """Random name for the guides a test creates; unique per test and lower case."""
    return f"{GUIDE_PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def qtag() -> str:
    """Random word for the chat messages a test sends, so they match no real guide."""
    return f"{MESSAGE_PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def admin_headers(client):
    from app.core.config import get_settings

    settings = get_settings()
    return {"X-Admin-Id": settings.ADMIN_ID, "X-Admin-Secret": settings.ADMIN_SECRET}