from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class TransactionFact:
    transaction_ref: str
    customer_id: str
    account_id: str
    value_date: date
    direction: Literal["CREDIT", "DEBIT"]
    amount: Decimal
    category: str
    is_international: bool = False
    status: Literal["BOOKED", "REVERSED", "PENDING"] = "BOOKED"
    is_internal_transfer: bool = False

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("transaction amount must be positive")


@dataclass(frozen=True, slots=True)
class BalanceFact:
    account_id: str
    as_of_date: date
    closing_balance: Decimal
    credit_limit: Decimal = Decimal(0)
    credit_used: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class FinancialMetric:
    code: str
    current_value: Decimal
    previous_value: Decimal | None
    growth_rate: Decimal | None
    change: Decimal | None
    historical_baseline: Decimal | None
    baseline_delta: Decimal | None
    sample_size: int
    data_coverage: Decimal
    quality_status: Literal["VALID", "INSUFFICIENT_HISTORY", "PARTIAL", "BASELINE_LOW"]
    seasonality_adjusted: bool


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    customer_id: str
    as_of_date: date
    window_days: int
    metrics: dict[str, FinancialMetric]
