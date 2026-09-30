import sqlite3

import pytest

import db
from inventory.schema import SCHEMA


@pytest.fixture
def conn(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db.init_db([SCHEMA])
    connection = db.get_connection()
    yield connection
    connection.close()


def test_default_locations_are_seeded(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM locations")}
    assert names == {"fridge", "pantry", "toiletries"}


def test_init_db_is_idempotent(conn):
    db.init_db([SCHEMA])  # running startup twice must not duplicate seed rows
    assert conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0] == 3


def test_negative_quantity_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO items (name, location_id, quantity) VALUES ('milk', 1, -1)")


def test_item_needs_a_valid_location(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO items (name, location_id) VALUES ('milk', 999)")
