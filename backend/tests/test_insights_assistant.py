import json
import os
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from whichcard.api import app
from whichcard.assistant import MockProvider, OpenAICompatibleProvider, Toolbox, ask
from whichcard.data_layer.models import WalletCard
from whichcard.importers import import_file
from whichcard.inference import enrich
from whichcard.insights import dismiss, generate_findings


def test_all_findings_and_dismissal(catalog, db):
    # The supplementary rotating-card fixture exercises an inactive category;
    # the four-card example wallet itself has no rotating product.
    catalog.wallet.cards.append(
        WalletCard(card="chase-freedom-flex", opened_on=date(2020, 1, 1), credit_limit=4000, statement_day=12)
    )
    import_file(db, Path("backend/tests/fixtures/rotation.csv"), "chase-freedom-flex")
    enrich(db, catalog)
    findings = generate_findings(catalog, db, date(2026, 10, 14))
    assert {f["kind"] for f in findings} >= {
        "misrouted_spend",
        "unused_credit",
        "fee_verdict",
        "signup_bonus_risk",
        "utilization",
        "dormancy",
        "rotation_inactive",
        "annual_fee_due",
        "idle_points",
        "data_quality",
    }
    for f in findings:
        if f["kind"] == "misrouted_spend":
            e = f["evidence"]
            assert f["dollar_impact"] == pytest.approx(
                round(e["loss_cents"] * e["annualization_factor"]) / 100, abs=0.01
            )
            assert all(
                db.execute('SELECT 1 FROM "transaction" WHERE id=?', (i,)).fetchone()
                for i in e["transaction_ids"]
            )
    fingerprint = findings[0]["fingerprint"]
    dismiss(db, fingerprint)
    assert fingerprint not in {f["fingerprint"] for f in generate_findings(catalog, db, date(2026, 10, 14))}
    with pytest.raises(ValueError):
        dismiss(db, "missing")


def test_mock_none_and_tools(catalog, db, monkeypatch):
    monkeypatch.setenv("WHICHCARD_TODAY", "2026-10-14")
    result = ask("How much dining?", catalog, db)
    assert result["provider"] == "none" and len(result["suggestions"]) == 6 and result["findings"]
    catalog.preferences.assistant.provider = "mock"
    result = ask("How much dining?", catalog, db)
    assert result["tool_calls"][0]["name"] == "spend_summary"
    toolbox = Toolbox(catalog, db)
    summary = json.loads(toolbox.call("spend_summary", {}))
    assert f"${summary['by_category']['dining'] / 100:.2f}" in result["answer"]
    assert db.execute("SELECT COUNT(*) FROM assistant_message").fetchone()[0] == 2
    for name, args in [
        ("findings", {}),
        ("card_rules", {"card_id": "amex-gold"}),
        ("card_rules", {}),
        ("recommend", {"context": {"category": "dining"}}),
        ("simulate_card", {"card_id": "amex-gold"}),
        ("transactions", {"filter": {"category": "gas"}}),
        ("trackers", {}),
    ]:
        result = toolbox.call(name, args)
        assert len(result) < 6000
        json.loads(result)
    with pytest.raises(ValueError):
        toolbox.call("run_shell", {})
    with pytest.raises(ValueError):
        ask("", catalog, db)
    assert "finding" in MockProvider().answer("fees?", toolbox)


def test_local_provider_tools_and_retrieval(catalog, db, monkeypatch):
    original = httpx.Client
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert request.url.host == "127.0.0.1"
        if len(seen) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "1",
                                        "type": "function",
                                        "function": {"name": "spend_summary", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "From spend_summary: computed local spending."}}]}
        )

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    catalog.preferences.assistant.supports_tools = True
    toolbox = Toolbox(catalog, db)
    assert "spend_summary" in OpenAICompatibleProvider(catalog).answer("Dining?", toolbox)
    assert any(m["role"] == "tool" for m in seen[-1]["messages"])
    assert "raw_description" not in json.dumps(seen)
    seen.clear()

    def reject_tools(request):
        payload = json.loads(request.content)
        seen.append(payload)
        if "tools" in payload:
            return httpx.Response(400, json={"error": "tools unsupported"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Computed summary."}}]})

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(reject_tools))
    )
    assert OpenAICompatibleProvider(catalog).answer("Dining?", Toolbox(catalog, db)) == "Computed summary."
    assert "Computed facts" in seen[-1]["messages"][0]["content"]
    catalog.preferences.assistant.supports_tools = False
    assert OpenAICompatibleProvider(catalog).answer("Dining?", Toolbox(catalog, db)) == "Computed summary."


def test_live_local_endpoint(catalog, db):
    url = os.environ.get("WHICHCARD_LIVE_LLM")
    if not url:
        pytest.skip("No local endpoint configured; set WHICHCARD_LIVE_LLM to opt in")
    catalog.preferences.assistant = catalog.preferences.assistant.model_validate(
        dict(
            provider="openai_compatible",
            base_url=url,
            model=os.environ.get("WHICHCARD_LIVE_MODEL", "llama3.2"),
        )
    )
    try:
        response = OpenAICompatibleProvider(catalog).answer("What data is available?", Toolbox(catalog, db))
    except httpx.HTTPError:
        pytest.skip("Local endpoint is not reachable")
    assert response


def test_insights_assistant_api(catalog, db, monkeypatch):
    from whichcard.api.service import database

    app.dependency_overrides[database] = lambda: db
    monkeypatch.setattr("whichcard.api.catalog", lambda: catalog)
    monkeypatch.setenv("WHICHCARD_TODAY", "2026-10-14")
    try:
        client = TestClient(app)
        findings = client.get("/api/findings").json()
        assert client.post("/api/findings/" + findings[0]["fingerprint"] + "/dismiss").status_code == 200
        assert client.post("/api/findings/missing/dismiss").status_code == 404
        assert client.post("/api/ask", json={"question": "Dining?"}).json()["provider"] == "none"
        assert client.post("/api/ask", json={"question": ""}).status_code == 422
    finally:
        app.dependency_overrides.clear()
