"""The safety net in main.py, checked without a database: any route that lets
InventoryUnavailable escape still answers 503 with JSON and CORS headers."""
from fastapi.testclient import TestClient

from app.inventory_client import InventoryUnavailable
from app.main import create_app


def test_inventory_unavailable_anywhere_becomes_a_503_with_cors(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080")
    app = create_app()

    @app.get("/boom")
    def boom():
        raise InventoryUnavailable("down")

    response = TestClient(app).get("/boom", headers={"Origin": "http://localhost:8080"})
    assert response.status_code == 503
    assert "not reachable" in response.json()["detail"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"
