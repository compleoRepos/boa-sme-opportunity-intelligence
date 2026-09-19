from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LifecyclePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validityDays: int = Field(default=90, ge=1, le=365)
    dismissedCooldownDays: int = Field(default=30, ge=1, le=365)
    convertedCooldownDays: int = Field(default=180, ge=1, le=730)
    deferredCooldownDays: int = Field(default=30, ge=1, le=365)
    expiredCooldownDays: int = Field(default=7, ge=1, le=90)


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleId: str | None = Field(default=None, min_length=1, max_length=80)
    version: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=4_000)
    status: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(min_length=1)
    logic: str = "AND"
    recommendation: dict[str, Any]
    confidence: dict[str, Any] = Field(default_factory=dict)
    lifecycle: LifecyclePolicy = Field(default_factory=LifecyclePolicy)
    reason: str | None = Field(default=None, max_length=4_000)


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=4_000)


class DuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=180)
    reason: str | None = Field(default=None, max_length=4_000)


class RollbackRequest(TransitionRequest):
    version: int = Field(ge=1)


class SimulationPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_: date = Field(alias="from")
    to: date

    @model_validator(mode="after")
    def valid_range(self) -> SimulationPeriod:
        if self.from_ > self.to:
            raise ValueError("period.from must not be after period.to")
        return self


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: SimulationPeriod
    population: dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customerId: str = Field(min_length=1, max_length=80)
    metrics: dict[str, Any]


__all__ = [
    "DuplicateRequest",
    "EvaluationRequest",
    "LifecyclePolicy",
    "RollbackRequest",
    "RuleDefinition",
    "SimulationRequest",
    "TransitionRequest",
]
