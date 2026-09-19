from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Scalar = float | int | bool | str


class ConditionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    operator: Literal["gt", "gte", "lt", "lte", "eq", "neq"]
    value: Scalar
    label: str


class LifecyclePolicyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    validity_days: int = Field(default=90, ge=1, le=365)
    dismissed_cooldown_days: int = Field(default=30, ge=1, le=365)
    converted_cooldown_days: int = Field(default=180, ge=1, le=730)
    deferred_cooldown_days: int = Field(default=30, ge=1, le=365)
    expired_cooldown_days: int = Field(default=7, ge=1, le=90)


class OpportunityRuleConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    version: str
    horizon: str
    what: str
    when: str
    all_conditions: tuple[ConditionConfig, ...] = ()
    any_conditions: tuple[ConditionConfig, ...] = ()
    recommended_product_codes: tuple[str, ...]
    confidence_weights: dict[str, float]
    priority_defaults: dict[str, float]
    minimum_data_coverage: float = Field(default=0.83, ge=0, le=1)
    lifecycle: LifecyclePolicyConfig = Field(default_factory=LifecyclePolicyConfig)

    @field_validator("confidence_weights")
    @classmethod
    def positive_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if not value or any(weight < 0 for weight in value.values()) or sum(value.values()) <= 0:
            raise ValueError("confidence weights must contain a positive total")
        return value


class SignalRuleConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    version: str
    metric: str
    value_field: Literal["current_value", "growth_rate", "change"]
    operator: Literal["gt", "gte", "lt", "lte"]
    threshold: float
    minimum_sample_size: int = Field(default=1, ge=1)
    require_confirmation: bool = True
    strong_evidence_margin: float = Field(default=0.50, ge=0)


class ConfidenceLevelsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    high: float = Field(default=0.75, ge=0, le=1)
    medium: float = Field(default=0.50, ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> ConfidenceLevelsConfig:
        if self.medium >= self.high:
            raise ValueError("medium confidence threshold must be below high")
        return self


class PriorityConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    weights: dict[str, float]
    p1: float = 80
    p2: float = 60
    p3: float = 40

    @model_validator(mode="after")
    def validate_priority(self) -> PriorityConfig:
        if not self.weights or any(value < 0 for value in self.weights.values()):
            raise ValueError("priority weights must be non-negative")
        if abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ValueError("priority weights must sum to one")
        if not self.p1 > self.p2 > self.p3:
            raise ValueError("priority thresholds must be descending")
        return self


class RuleSetConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    config_id: str
    engine_version: str
    rule_set_version: str
    status: Literal["DRAFT", "APPROVED", "ACTIVE", "RETIRED", "ROLLED_BACK"]
    effective_from: str
    created_by: str
    approved_by: str
    change_reason: str
    confidence_levels: ConfidenceLevelsConfig
    priority: PriorityConfig
    signal_rules: dict[str, SignalRuleConfig]
    opportunity_rules: dict[str, OpportunityRuleConfig]

    @model_validator(mode="after")
    def exactly_four_mvp_rules(self) -> RuleSetConfig:
        required = {
            "INVESTMENT_FINANCING",
            "TRADE_FINANCE",
            "CASH_INVESTMENT",
            "FINANCIAL_STRESS_SIGNAL",
        }
        if set(self.opportunity_rules) != required:
            raise ValueError(f"opportunity rules must be exactly {sorted(required)}")
        if self.status == "ACTIVE" and not self.approved_by:
            raise ValueError("an active rule set must be approved")
        return self

    def checksum(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_rules_path() -> Path:
    configured = os.getenv("BOA_RULES_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "database" / "seed" / "rules.yaml"


def load_rule_set(path: str | Path | None = None) -> RuleSetConfig:
    source = Path(path) if path else default_rules_path()
    with source.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)
    return RuleSetConfig.model_validate(raw)


@lru_cache(maxsize=1)
def active_rule_set() -> RuleSetConfig:
    rules = load_rule_set()
    if rules.status != "ACTIVE":
        raise ValueError("configured rule set is not ACTIVE")
    return rules
