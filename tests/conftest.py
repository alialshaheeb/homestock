"""Shared fixtures: every test gets its own empty SQLite file in a temp DATA_DIR."""
import pytest
from fastapi.testclient import TestClient

import db
from inventory.schema import SCHEMA as INVENTORY_SCHEMA


@pytest.fixture
def conn(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db.init_db([INVENTORY_SCHEMA])
    connection = db.get_connection()
    yield connection
    connection.close()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app as app_module

    with TestClient(app_module.create_app()) as test_client:
        yield test_client
