from fastapi.testclient import TestClient
from whichcard.api import app


def test_health():
    assert TestClient(app).get("/api/health").json()["status"] == "ok"
