"""Test fixtures. Database tests run against a real SQL Server test database named in
TEST_DATABASE_URL (skipped without it). The inventory service is replaced by FakeInventory,
an in-memory stand-in with the same three calls as app/inventory_client.py."""
import os
import re
from urllib.parse import urlparse, urlunparse

import pytest
from fastapi.testclient import TestClient

from app import db, inventory_client
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
    """A connection to an emptied test database."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    connection = db.connect(database_url)
    connection.cursor().execute("DELETE FROM shopping_list")
    connection.commit()
    yield connection
    connection.close()


class FakeInventory:
    """Items keyed by id, as the inventory service would return them. `down=True` makes
    every call fail the way inventory_client does when the service is unreachable."""

    def __init__(self):
        self.items: dict[int, dict] = {}
        self.down = False

    def add(self, item_id, name="milk", quantity=1.0, min_threshold=0.0, unit="pcs"):
        self.items[item_id] = {"id": item_id, "name": name, "quantity": quantity,
                               "min_threshold": min_threshold, "unit": unit}
        return self.items[item_id]

    def _check(self):
        if self.down:
            raise inventory_client.InventoryUnavailable("inventory service unreachable")

    def low_stock_items(self):
        self._check()
        return [i for i in self.items.values() if 0 < i["min_threshold"] and i["quantity"] <= i["min_threshold"]]

    def get_item(self, item_id):
        self._check()
        return self.items.get(item_id)

    def add_stock(self, item_id, amount):
        self._check()
        if item_id not in self.items:
            return False
        self.items[item_id]["quantity"] += amount
        return True


@pytest.fixture
def inventory(monkeypatch):
    fake = FakeInventory()
    for name in ("low_stock_items", "get_item", "add_stock"):
        monkeypatch.setattr(inventory_client, name, getattr(fake, name))
    return fake


@pytest.fixture
def client(conn, inventory):
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
