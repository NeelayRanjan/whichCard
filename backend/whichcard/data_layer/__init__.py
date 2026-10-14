from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import TypeAdapter, ValidationError

from .models import (
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

T = TypeVar("T")
ROOT = Path(os.environ.get("WHICHCARD_ROOT", Path(__file__).resolve().parents[3]))


def read_yaml(path: Path, schema: Any) -> Any:
    text = path.read_text()
    try:
        raw = yaml.safe_load(text)
        return TypeAdapter(schema).validate_python(raw)
    except (yaml.YAMLError, ValidationError, ValueError) as exc:
        line = getattr(getattr(exc, "problem_mark", None), "line", 0) + 1
        if isinstance(exc, ValidationError):
            node = yaml.compose(text)
            for key in exc.errors()[0]["loc"]:
                if isinstance(node, yaml.MappingNode):
                    node = next((v for k, v in node.value if str(k.value) == str(key)), node)
                elif isinstance(node, yaml.SequenceNode) and isinstance(key, int) and key < len(node.value):
                    node = node.value[key]
            if node:
                line = node.start_mark.line + 1
        raise ValueError(f"{path}:{line}: {exc}") from exc


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(yaml.safe_dump(value, sort_keys=False))
    temp.replace(path)


class Catalog:
    def __init__(self, root: Path = ROOT):
        self.root = root
        data, config = root / "data", root / "config"
        wallet = config / "wallet.yaml"
        if not wallet.exists():
            shutil.copyfile(config / "wallet.example.yaml", wallet)
        self.cards: dict[str, Card] = {}
        for path in sorted((data / "cards").glob("*.yaml")):
            card = read_yaml(path, Card)
            if card.id in self.cards:
                raise ValueError(f"{path}:1: duplicate card id {card.id}")
            self.cards[card.id] = card
        self.wallet: Wallet = read_yaml(wallet, Wallet)
        self.preferences: Preferences = read_yaml(self.config_path("preferences"), Preferences)
        self.valuations: dict[str, Valuation] = read_yaml(data / "valuations.yaml", dict[str, Valuation])
        self.transfers: dict[str, list[Transfer]] = read_yaml(
            data / "transfer_partners.yaml", dict[str, list[Transfer]]
        )
        self.categories: dict[str, Category] = read_yaml(data / "mcc/categories.yaml", dict[str, Category])
        self.patterns: list[Pattern] = read_yaml(data / "merchants/patterns.yaml", list[Pattern])
        learned = data / "merchants/learned.local.yaml"
        self.learned: list[Pattern] = read_yaml(
            learned if learned.exists() else data / "merchants/learned.yaml", list[Pattern]
        )
        self.apps: dict[str, AppContext] = read_yaml(data / "app_contexts.yaml", dict[str, AppContext])
        self.programs: dict[str, LoungeProgram] = read_yaml(
            data / "lounges/programs.yaml", dict[str, LoungeProgram]
        )
        self.lounges: dict[str, list[Lounge]] = read_yaml(
            data / "lounges/airports.yaml", dict[str, list[Lounge]]
        )
        self.places: list[Place] = read_yaml(self.config_path("places"), list[Place])
        self.offers: list[Offer] = read_yaml(self.config_path("offers"), list[Offer])
        for instance in self.wallet.cards:
            if instance.card not in self.cards:
                raise ValueError(f"{wallet}:1: unknown card {instance.card}")
        for card in self.cards.values():
            if card.currency not in self.valuations:
                raise ValueError(f"{data}/cards/{card.id}.yaml:1: unknown currency {card.currency}")
            for rule in card.earn:
                if (
                    rule.match.category
                    and rule.match.category not in self.categories
                    and rule.match.category != "chosen"
                ):
                    raise ValueError(f"{data}/cards/{card.id}.yaml:1: unknown category")
        for lounges in self.lounges.values():
            for lounge in lounges:
                if any(p not in self.programs for p in lounge.programs):
                    raise ValueError(f"{data}/lounges/airports.yaml:1: unknown program")

    def config_path(self, name: str) -> Path:
        local = self.root / f"config/{name}.local.yaml"
        return local if local.exists() else self.root / f"config/{name}.yaml"

    def valuation(self, currency: str) -> Valuation:
        return self.preferences.valuations.get(currency, self.valuations[currency])

    def review(self) -> str:
        wallet = {c.card for c in self.wallet.cards}
        cards = sorted(self.cards.values(), key=lambda c: (c.id not in wallet, c.issuer, c.name))
        return (
            "# Review unverified card data\n\nCheck issuer terms before relying on recommendations. "
            "All values are estimates, not verified offers.\n\n"
            "| Card | Confidence | Fields to check | Verified |\n|---|---|---|---|\n"
            + "\n".join(f"| {c.name} ({c.id}) | {c.confidence} | {c.notes} | |" for c in cards)
            + "\n\nAlso review valuations, transfer ratios/times and lounge admission/guest rules. "
            "Airport coordinates are vendored from the public-domain OurAirports dataset.\n"
        )
