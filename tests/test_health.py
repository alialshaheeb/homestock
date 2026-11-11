import os
import tempfile

from fastapi.testclient import TestClient


def test_health_creates_db_and_returns_ok(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATA_DIR", tmp)
        import app as app_module

        with TestClient(app_module.create_app()) as client:
            assert client.get("/health").json() == {"status": "ok"}
        assert os.path.exists(os.path.join(tmp, "homestock.db"))


def test_ui_is_served_at_root(client):
    page = client.get("/")
    assert page.status_code == 200 and "HomeStock" in page.text
    assert client.get("/app.js?v=3").status_code == 200
    assert page.headers["cache-control"] == "no-cache"  # browsers recheck, so UI updates show up
