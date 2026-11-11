"""Test fixtures. Database tests run against a real SQL Server test database named in
TEST_DATABASE_URL (in CI a SQL Server service container; locally the compose one, see the
README). Without it they are skipped, and only the tests that need no database run."""
import os
import re
from urllib.parse import urlparse, urlunparse

import pytest
from fastapi.testclient import TestClient

from app import db, service
from app.migrations import migrate

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _create_database_if_missing(url: str) -> None:
    parts = urlparse(url)
    name = parts.path.lstrip("/")
    assert re.fullmatch(r"\w+", name), "test database name must be letters, digits or _"
    master = db.connect(urlunparse(parts._replace(path="/master")))
    master.autocommit(True)  # CREATE DATABASE cannot run inside a transaction
    master.cursor().execute(f"IF DB_ID('{name}') IS NULL CREATE DATABASE {name}")
    master.close()


@pytest.fixture(scope="session")
def database_url():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    _create_database_if_missing(TEST_DATABASE_URL)
    conn = db.connect(TEST_DATABASE_URL)
    migrate(conn)
    conn.close()
    return TEST_DATABASE_URL


@pytest.fixture
def conn(database_url, monkeypatch):
    """A connection to an emptied test database with only the seed places in it."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    connection = db.connect(database_url)
    cursor = connection.cursor()
    cursor.execute("DELETE FROM items")
    cursor.execute("DELETE FROM locations")
    connection.commit()
    service.seed(connection)
    yield connection
    connection.close()


@pytest.fixture
def client(conn):
    """The whole app over HTTP, on the same test database (start-up runs migrations + seed)."""
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
