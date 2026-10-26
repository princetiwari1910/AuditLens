"""Smoke test for the health endpoint."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["provider_mode"] in ("mock", "meta")
