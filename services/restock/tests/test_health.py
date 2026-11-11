from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_503_with_json_when_the_database_is_unreachable(monkeypatch):
    # Nothing listens on port 1. TestClient without `with` skips start-up, so no retries.
    monkeypatch.setenv("DATABASE_URL", "mssql://u:p@127.0.0.1:1/db")
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_health_is_200_with_db_and_version(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["db"] == "ok" and "version" in body


def test_cors_allows_only_the_configured_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:8080")
    monkeypatch.setenv("DATABASE_URL", "mssql://u:p@127.0.0.1:1/db")
    client = TestClient(create_app())
    ok = client.options("/shopping-list", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"})
    bad = client.options("/shopping-list", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8080"
    assert "access-control-allow-origin" not in bad.headers
