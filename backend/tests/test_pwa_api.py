from fastapi.testclient import TestClient
from whichcard.api import app
from whichcard.api.service import database


def test_settings_transactions_import(catalog, db, monkeypatch):
    monkeypatch.setattr("whichcard.api.catalog", lambda: catalog)
    app.dependency_overrides[database] = lambda: db
    try:
        client = TestClient(app)
        cfg = client.get("/api/config").json()
        assert client.put("/api/settings", json=cfg["preferences"]).status_code == 200
        assert client.put("/api/wallet", json=cfg["wallet"]).status_code == 200
        assert client.put("/api/offers", json=[]).status_code == 200
        assert (
            client.put(
                "/api/settings", json={"assistant": {"base_url": "https://outside.example"}}
            ).status_code
            == 422
        )
        invalid = cfg["wallet"]
        invalid["cards"][0]["last4"] = "1234567812345678"
        assert client.put("/api/wallet", json=invalid).status_code == 422
        rows = client.get("/api/transactions?limit=3").json()
        assert len(rows["rows"]) == 3
        assert client.get("/api/transactions?limit=0").status_code == 422
        assert (
            client.post(
                f"/api/transactions/{rows['rows'][0]['id']}/override",
                json={"field": "category", "value": "other"},
            ).status_code
            == 200
        )
        assert (
            client.post("/api/transactions/999999/override", json={"field": "bad", "value": "x"}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/statements",
                json={"wallet_card_id": "amex-gold", "close_date": "2026-10-01", "statement_balance": 1000},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/statements",
                json={"wallet_card_id": "missing", "close_date": "2026-10-01", "statement_balance": 1000},
            ).status_code
            == 422
        )
        response = client.post(
            "/api/import",
            files={"file": ("new.csv", b"Date,Description,Amount\n2026-10-13,STARBUCKS,12.34\n")},
            data={"card": "amex-gold"},
        )
        assert response.status_code == 200 and response.json()["added"] == 1
        assert (
            client.post(
                "/api/import", files={"file": ("bad.txt", b"x")}, data={"card": "amex-gold"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/import", files={"file": ("bad.csv", b"description\nX")}, data={"card": "amex-gold"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/import", files={"file": ("bad.csv", b"x")}, data={"card": "missing"}
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/offers",
                json=[
                    {
                        "wallet_card": "missing",
                        "merchant_pattern": "x",
                        "type": "fixed",
                        "value": 1,
                        "expires": "2027-01-01",
                    }
                ],
            ).status_code
            == 422
        )
        assert client.get("/api/missing").status_code == 404
        assert (
            client.put(
                "/api/settings", json=cfg["preferences"], headers={"Origin": "https://bad.example"}
            ).status_code
            == 403
        )
    finally:
        app.dependency_overrides.clear()
