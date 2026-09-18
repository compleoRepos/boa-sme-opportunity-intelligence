from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpportunityContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: str
    as_of_date: date
    facts: dict[str, float | int | bool | str]
    data_coverage: float = Field(default=1.0, ge=0, le=1)
    data_quality: Literal["VALID", "PARTIAL", "DATA_INVALID", "INSUFFICIENT_HISTORY"] = "VALID"
    seasonality_adjusted: bool = True
    false_positive_flags: tuple[str, ...] = ()
    confidence_factors: dict[str, float | None] = {}
    priority_factors: dict[str, float | None] = {}


class ConditionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    operator: str
    expected: Any
    observed: Any
    passed: bool
    label: str


class OpportunityCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    opportunity_id: str
    customer_id: str
    opportunity_type: str
    status: Literal["OPEN"] = "OPEN"
    horizon: str
    confidence: float
    confidence_level: Literal["LOW", "MEDIUM", "HIGH"]
    confidence_components: tuple[dict[str, Any], ...]
    priority_score: float
    priority_level: Literal["P1", "P2", "P3", "P4"]
    priority_components: tuple[dict[str, Any], ...]
    why: tuple[str, ...]
    what: str
    when: str
    recommended_products: tuple[str, ...]
    evidence: tuple[ConditionEvidence, ...]
    as_of_date: date
    generated_at: str
    engine_version: str
    rule_version: str
    rule_set_version: str
