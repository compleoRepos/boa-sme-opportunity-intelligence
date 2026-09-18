from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetricObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    current_value: float
    previous_value: float | None = None
    growth_rate: float | None = None
    change: float | None = None
    historical_baseline: float | None = None
    sample_size: int = Field(default=1, ge=0)
    data_coverage: float = Field(default=1.0, ge=0, le=1)
    quality_status: Literal[
        "VALID", "PARTIAL", "INSUFFICIENT_HISTORY", "BASELINE_LOW", "DATA_INVALID"
    ] = "VALID"
    seasonality_adjusted: bool = True
    confirmation_count: int = Field(default=2, ge=0)


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    customer_id: str
    signal_type: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    status: Literal["OBSERVED", "CONFIRMED"]
    value: float
    threshold: float
    period: str
    as_of_date: date
    evidence: tuple[str, ...]
    metric_reference: str
    rule_version: str
