from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_regex(value: str) -> None:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"invalid regex: {exc}") from exc


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Match(Model):
    category: str | None = None
    merchant_id: str | None = None
    merchant_pattern: str | None = None
    channel: Literal["in_person", "online", "recurring"] | None = None
    portal: str | None = None
    mcc: list[int] | None = None
    app_context: str | None = None
    any: bool = False

    @field_validator("merchant_pattern")
    @classmethod
    def regex(cls, value: str | None) -> str | None:
        if value is not None:
            validate_regex(value)
        return value


class Cap(Model):
    amount: float = Field(gt=0)
    period: Literal["month", "quarter", "annual"]
    basis: Literal["calendar", "anniversary"] = "calendar"
    group: str | None = None


class Active(Model):
    from_: date = Field(alias="from")
    to: date
    requires_activation: bool = False

    @model_validator(mode="after")
    def ordered(self) -> Active:
        if self.to < self.from_:
            raise ValueError("active end precedes start")
        return self


class Earn(Model):
    match: Match
    rate: float = Field(ge=0, le=30)
    cap: Cap | None = None
    active: Active | None = None


class Credit(Model):
    id: str
    name: str
    amount: float = Field(ge=0)
    period: Literal["month", "quarter", "annual"]
    reset: Literal["anniversary", "calendar"]
    match: Match


class Perks(Model):
    lounge_programs: list[str] = []
    no_foreign_fee: bool = False
    other: list[str] = []


class Bonus(Model):
    points: int = Field(ge=0)
    min_spend: float = Field(ge=0)
    window_days: int = Field(gt=0)


class Card(Model):
    id: str
    issuer: str
    name: str
    network: Literal["visa", "mastercard", "amex", "discover"]
    currency: str
    annual_fee: float = Field(ge=0)
    foreign_transaction_fee: float = Field(ge=0, le=1)
    confidence: Literal["low", "medium", "high"]
    verified_on: date | None
    notes: str
    earn: list[Earn] = Field(min_length=1)
    credits: list[Credit] = []
    perks: Perks = Perks()
    signup_bonus: Bonus | None = None
    product_change_targets: list[str] = []


class WalletBonus(Model):
    min_spend: float = Field(gt=0)
    deadline: date
    completed: bool = False


class WalletCard(Model):
    card: str
    nickname: str | None = None
    last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    opened_on: date
    credit_limit: float = Field(gt=0)
    statement_day: int = Field(ge=1, le=31)
    signup_bonus: WalletBonus | None = None
    authorized_user: bool = False
    settings: dict[str, str | bool] = {}


class Inquiry(Model):
    date: date
    note: str = ""


class Balance(Model):
    currency: str
    amount: int = Field(ge=0)
    as_of: date


class Wallet(Model):
    cards: list[WalletCard]
    inquiries: list[Inquiry] = []
    balances: list[Balance] = []

    @model_validator(mode="after")
    def unique(self) -> Wallet:
        if len({c.card for c in self.cards}) != len(self.cards):
            raise ValueError("v1 supports one wallet instance per card id")
        return self


class Valuation(Model):
    cash_out: float = Field(gt=0)
    typical: float = Field(gt=0)
    optimized: float = Field(gt=0)
    source_note: str = "User override; not a guaranteed redemption value."

    @model_validator(mode="after")
    def ordered(self) -> Valuation:
        if not self.cash_out <= self.typical <= self.optimized:
            raise ValueError("require cash_out <= typical <= optimized")
        return self


class AssistantConfig(Model):
    provider: Literal["none", "mock", "openai_compatible"] = "none"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.2"
    supports_tools: bool = False

    @field_validator("base_url")
    @classmethod
    def local_only(cls, value: str) -> str:
        from urllib.parse import urlparse

        url = urlparse(value)
        if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.username:
            raise ValueError("assistant must use http on localhost/127.0.0.1/::1")
        return value.rstrip("/")


class Targets(Model):
    per_card: float = Field(default=30, gt=0, le=100)
    total: float = Field(default=10, gt=0, le=100)


class Server(Model):
    bind: str = "0.0.0.0"
    port: int = Field(default=8787, ge=1, le=65535)


class Preferences(Model):
    valuations: dict[str, Valuation] = {}
    goal: Literal["cash", "travel", "balanced"] = "balanced"
    home_airports: list[str] = ["SFO"]
    utilization_targets: Targets = Targets()
    assistant: AssistantConfig = AssistantConfig()
    server: Server = Server()
    perk_values: dict[str, float] = {}
    idle_points_threshold: int = 10000


class Transfer(Model):
    partner: str
    ratio: float = Field(gt=0)
    typical_days: float = Field(ge=0)
    notes: str = "Unverified seed: confirm ratio, eligibility and transfer time."


class Category(Model):
    mcc_ranges: list[tuple[int, int]] = []
    issuer_names: dict[str, list[str]]


class Pattern(Model):
    pattern: str
    merchant_id: str
    display_name: str
    category: str
    mcc: int | None = None
    confidence: float = Field(ge=0, le=1)

    @field_validator("pattern")
    @classmethod
    def valid_regex(cls, value: str) -> str:
        validate_regex(value)
        return value


class Alternative(Model):
    app: str
    perk: str


class AppContext(Model):
    category: str
    channel: Literal["online", "in_person", "recurring"]
    alternatives: list[Alternative] = []


class LoungeProgram(Model):
    name: str
    guest_rules: str
    notes: str


class Lounge(Model):
    name: str
    terminal: str
    programs: list[str]
    confidence: Literal["low", "medium", "high"] = "low"
    notes: str = "Unverified seed: confirm location, opening hours and admission restrictions."


class Place(Model):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    merchant_id: str
    radius_m: float = Field(gt=0, le=10000)


class Offer(Model):
    wallet_card: str
    merchant_pattern: str
    type: Literal["percent", "fixed"]
    value: float = Field(ge=0)
    min_spend: float = Field(default=0, ge=0)
    expires: date

    @field_validator("merchant_pattern")
    @classmethod
    def regex(cls, value: str) -> str:
        validate_regex(value)
        return value
