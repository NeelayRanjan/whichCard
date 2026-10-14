from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner
from whichcard.cli import app
from whichcard.data_layer import Catalog, read_yaml
from whichcard.data_layer.models import (
    AppContext,
    Card,
    Category,
    Lounge,
    LoungeProgram,
    Offer,
    Pattern,
    Place,
    Preferences,
    Transfer,
    Valuation,
    Wallet,
)


def test_catalog():
    c = Catalog()
    assert len(c.cards) >= 36
    assert len(c.lounges) >= 50
    assert len(c.wallet.cards) == 4
    assert all(x.confidence != "high" and x.verified_on is None for x in c.cards.values())
    assert c.valuation("chase-ur").typical == 1.5
    assert "Sapphire Preferred" in c.review()
    assert CliRunner().invoke(app, ["cards", "list"]).exit_code == 0


@pytest.mark.parametrize(
    "schema",
    [
        Card,
        Wallet,
        Preferences,
        Valuation,
        Transfer,
        Category,
        Pattern,
        AppContext,
        LoungeProgram,
        Lounge,
        Place,
        Offer,
    ],
)
def test_negative_schema(tmp_path, schema):
    p = tmp_path / "broken.yaml"
    p.write_text("unexpected: true\n")
    with pytest.raises(ValueError, match="broken.yaml:1:"):
        read_yaml(p, schema)


def test_yaml_error_line(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("cash_out: 1\ntypical: -2\noptimized: 3\n")
    with pytest.raises(ValueError, match="bad.yaml:2:"):
        read_yaml(p, Valuation)
    p.write_text("a: [\n")
    with pytest.raises(ValueError, match="bad.yaml:"):
        read_yaml(p, dict)


def test_config_validation(tmp_path):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Preferences(assistant={"base_url": "https://external.example", "provider": "openai_compatible"})
    with pytest.raises(ValidationError):
        Pattern(pattern="[", merchant_id="a", display_name="a", category="other", confidence=1)
    p = tmp_path / "wallet.yaml"
    raw = yaml.safe_load(Path("config/wallet.example.yaml").read_text())
    raw["cards"][0]["last4"] = "1234567890123456"
    p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="last4"):
        read_yaml(p, Wallet)
