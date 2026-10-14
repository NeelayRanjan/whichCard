"""Boot a real server with isolated synthetic state and exercise every UI endpoint."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from whichcard.data_layer import ROOT, Catalog
from whichcard.importers import import_file
from whichcard.inference import enrich
from whichcard.storage import connect


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="whichcard-smoke-") as directory:
        root = Path(directory)
        for name in ["data", "config", "backend/migrations", "frontend/dist"]:
            shutil.copytree(
                ROOT / name, root / name, ignore=shutil.ignore_patterns("*.local.yaml", "wallet.yaml")
            )
        catalog = Catalog(root)
        path = root / "var/fixture.db"
        db = connect(path)
        for card in catalog.wallet.cards:
            import_file(db, ROOT / f"backend/tests/fixtures/{card.card}.csv", card.card)
        enrich(db, catalog)
        db.close()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, WHICHCARD_DB=str(path), WHICHCARD_ROOT=str(root), WHICHCARD_TODAY="2026-10-14")
        log = (root / "server.log").open("w+")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "whichcard.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if process.poll() is not None:
                        raise AssertionError("Server exited before readiness")
                    time.sleep(0.1)
                else:
                    raise AssertionError("Server did not become ready")

                def check(method, path, **kwargs):
                    response = client.request(method, path, **kwargs)
                    assert response.status_code == 200, (
                        method,
                        path,
                        response.status_code,
                        response.text[:1000],
                    )
                    return (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else response.text
                    )

                for endpoint in [
                    "/",
                    "/manifest.webmanifest",
                    "/sw.js",
                    "/icon-192.png",
                    "/icon-512.png",
                    "/api/health",
                    "/api/config",
                    "/api/trackers",
                    "/api/transactions",
                    "/api/transactions?review=true",
                    "/api/spend",
                    "/api/gap",
                    "/api/airport/SFO",
                ]:
                    check("GET", endpoint)
                for query in [
                    "app=ubereats",
                    "category=dining",
                    "merchant=costco",
                    "lat=37.619&lon=-122.375",
                ]:
                    assert len(check("GET", "/api/now?" + query)["notification_text"]) < 120
                recommendation = check(
                    "POST", "/api/recommend", json={"merchant_query": "costco", "amount_cents": 18000}
                )
                assert recommendation["ranked"][0]["reasons"] and recommendation["ranked"][0]["range"]
                check(
                    "POST",
                    "/api/redeem/evaluate",
                    json={"cash_price_cents": 40000, "awards": [{"program": "united", "points": 20000}]},
                )
                cfg = check("GET", "/api/config")
                check("PUT", "/api/settings", json=cfg["preferences"])
                check("PUT", "/api/wallet", json=cfg["wallet"])
                check("PUT", "/api/offers", json=[])
                check(
                    "POST",
                    "/api/places",
                    json={
                        "name": "Test coffee",
                        "lat": 0,
                        "lon": 0,
                        "merchant_id": "starbucks",
                        "radius_m": 100,
                    },
                )
                check(
                    "POST",
                    "/api/statements",
                    json={
                        "wallet_card_id": "bofa-customized-cash",
                        "close_date": "2026-10-12",
                        "statement_balance": 120000,
                    },
                )
                check("POST", "/api/credits/amex-gold/uber", json={"amount_cents": 1000})
                row = check("GET", "/api/transactions?review=true")["rows"][0]
                check(
                    "POST",
                    f"/api/transactions/{row['id']}/override",
                    json={"field": "category", "value": "other"},
                )
                with (ROOT / "backend/tests/fixtures/amex-gold.csv").open("rb") as f:
                    assert (
                        check(
                            "POST",
                            "/api/import",
                            files={"file": ("gold.csv", f, "text/csv")},
                            data={"card": "amex-gold"},
                        )["added"]
                        == 0
                    )
                findings = check("GET", "/api/findings")
                check("POST", f"/api/findings/{findings[0]['fingerprint']}/dismiss", json={})
                assert check("POST", "/api/ask", json={"question": "Dining spend?"})["provider"] == "none"
                cfg["preferences"]["assistant"]["provider"] = "mock"
                check("PUT", "/api/settings", json=cfg["preferences"])
                assert (
                    check("POST", "/api/ask", json={"question": "Dining spend?"})["tool_calls"][0]["name"]
                    == "spend_summary"
                )
                assert client.post("/api/recommend", json={"amount_cents": -1}).status_code == 422
                assert client.get("/api/does-not-exist").status_code == 404
                assert (
                    client.post(
                        "/api/ask", headers={"Origin": "https://external.example"}, json={"question": "hi"}
                    ).status_code
                    == 403
                )
            print("Smoke passed: production PWA and every UI read/write endpoint against isolated fixtures.")
        except Exception:
            log.seek(0)
            print(log.read()[-6000:])
            raise
        finally:
            process.terminate()
            process.wait(timeout=10)
            log.close()


if __name__ == "__main__":
    main()
