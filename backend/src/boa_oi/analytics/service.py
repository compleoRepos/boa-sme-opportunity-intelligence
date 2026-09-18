from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal

from .domain import BalanceFact, FinancialMetric, MetricSnapshot, TransactionFact

ZERO = Decimal(0)
ONE = Decimal(1)
SUPPORTED_WINDOWS = frozenset({7, 30, 90, 180, 365})


def growth_rate(
    current: Decimal, previous: Decimal, denominator_floor: Decimal
) -> tuple[Decimal | None, Literal["VALID", "BASELINE_LOW"]]:
    if denominator_floor <= 0:
        raise ValueError("denominator floor must be positive")
    if abs(previous) < denominator_floor:
        return None, "BASELINE_LOW"
    return (current - previous) / max(abs(previous), denominator_floor), "VALID"


class AnalyticsEngine:
    """Pure, deterministic financial metric calculator."""

    def __init__(self, denominator_floors: dict[str, Decimal] | None = None) -> None:
        self.denominator_floors = denominator_floors or {
            "inflow_amount": Decimal(1000),
            "outflow_amount": Decimal(1000),
            "supplier_payment_amount": Decimal(1000),
            "international_flow_amount": Decimal(1000),
            "transaction_count": Decimal(1),
            "average_balance": Decimal(1000),
            "credit_line_utilization": Decimal("0.01"),
        }

    @staticmethod
    def _range(as_of: date, days: int, offset: int = 0) -> tuple[date, date]:
        end = as_of - timedelta(days=offset)
        return end - timedelta(days=days - 1), end

    @staticmethod
    def _valid_transactions(
        transactions: Iterable[TransactionFact], start: date, end: date
    ) -> list[TransactionFact]:
        return [
            item
            for item in transactions
            if start <= item.value_date <= end
            and item.status == "BOOKED"
            and not item.is_internal_transfer
        ]

    @staticmethod
    def _balances(balances: Iterable[BalanceFact], start: date, end: date) -> list[BalanceFact]:
        return [item for item in balances if start <= item.as_of_date <= end]

    @staticmethod
    def _aggregate_transactions(items: list[TransactionFact]) -> dict[str, Decimal]:
        return {
            "inflow_amount": sum(
                (item.amount for item in items if item.direction == "CREDIT"), ZERO
            ),
            "outflow_amount": sum(
                (item.amount for item in items if item.direction == "DEBIT"), ZERO
            ),
            "supplier_payment_amount": sum(
                (
                    item.amount
                    for item in items
                    if item.direction == "DEBIT" and item.category == "SUPPLIER_PAYMENT"
                ),
                ZERO,
            ),
            "international_flow_amount": sum(
                (item.amount for item in items if item.is_international), ZERO
            ),
            "transaction_count": Decimal(len(items)),
            "international_transaction_count": Decimal(
                sum(1 for item in items if item.is_international)
            ),
        }

    @staticmethod
    def _aggregate_balances(items: list[BalanceFact]) -> dict[str, Decimal]:
        if not items:
            return {
                "average_balance": ZERO,
                "minimum_balance": ZERO,
                "maximum_balance": ZERO,
                "credit_line_utilization": ZERO,
                "surplus_day_ratio": ZERO,
            }
        daily: dict[date, Decimal] = defaultdict(Decimal)
        utilization_numerator: dict[date, Decimal] = defaultdict(Decimal)
        utilization_limit: dict[date, Decimal] = defaultdict(Decimal)
        for item in items:
            daily[item.as_of_date] += item.closing_balance
            utilization_numerator[item.as_of_date] += max(item.credit_used, ZERO)
            utilization_limit[item.as_of_date] += max(item.credit_limit, ZERO)
        values = list(daily.values())
        utilizations = [
            min(ONE, utilization_numerator[day] / utilization_limit[day])
            if utilization_limit[day] > 0
            else ZERO
            for day in daily
        ]
        return {
            "average_balance": sum(values, ZERO) / Decimal(len(values)),
            "minimum_balance": min(values),
            "maximum_balance": max(values),
            "credit_line_utilization": sum(utilizations, ZERO) / Decimal(len(utilizations)),
            "surplus_day_ratio": Decimal(sum(1 for value in values if value > Decimal(1000000)))
            / Decimal(len(values)),
        }

    def calculate(
        self,
        customer_id: str,
        transactions: Iterable[TransactionFact],
        balances: Iterable[BalanceFact],
        as_of_date: date,
        window_days: int,
        *,
        historical_values: dict[str, list[Decimal]] | None = None,
    ) -> MetricSnapshot:
        if window_days not in SUPPORTED_WINDOWS:
            raise ValueError(f"unsupported window: {window_days}")
        tx = tuple(transactions)
        balance_rows = tuple(balances)
        if any(item.customer_id != customer_id for item in tx):
            raise ValueError("transactions from another customer are not allowed")
        current_start, current_end = self._range(as_of_date, window_days)
        previous_start, previous_end = self._range(as_of_date, window_days, window_days)
        current_tx = self._valid_transactions(tx, current_start, current_end)
        previous_tx = self._valid_transactions(tx, previous_start, previous_end)
        current_balances = self._balances(balance_rows, current_start, current_end)
        previous_balances = self._balances(balance_rows, previous_start, previous_end)
        current = self._aggregate_transactions(current_tx) | self._aggregate_balances(
            current_balances
        )
        previous = self._aggregate_transactions(previous_tx) | self._aggregate_balances(
            previous_balances
        )
        covered_days = len({item.as_of_date for item in current_balances})
        coverage = (
            min(ONE, Decimal(covered_days) / Decimal(window_days)) if current_balances else ZERO
        )
        quality = "VALID" if coverage >= Decimal("0.83") else "PARTIAL"
        metrics: dict[str, FinancialMetric] = {}
        for code, current_value in current.items():
            previous_value = previous.get(code)
            floor = self.denominator_floors.get(code, Decimal("0.01"))
            rate, rate_quality = growth_rate(current_value, previous_value or ZERO, floor)
            history = (historical_values or {}).get(code, [])
            baseline = Decimal(str(median(history))) if history else None
            baseline_delta = None
            if baseline is not None and abs(baseline) >= floor:
                baseline_delta = (current_value - baseline) / max(abs(baseline), floor)
            seasonality_adjusted = coverage >= Decimal("0.83") and (
                baseline_delta is None
                or rate is None
                or ((rate >= 0 and baseline_delta >= 0) or (rate < 0 and baseline_delta < 0))
            )
            metric_quality: Literal["VALID", "PARTIAL", "BASELINE_LOW"]
            if rate_quality == "BASELINE_LOW":
                metric_quality = "BASELINE_LOW"
            elif quality == "PARTIAL":
                metric_quality = "PARTIAL"
            else:
                metric_quality = "VALID"
            sample_size = (
                len(current_balances)
                if code
                in {
                    "average_balance",
                    "minimum_balance",
                    "maximum_balance",
                    "credit_line_utilization",
                    "surplus_day_ratio",
                }
                else len(current_tx)
            )
            metrics[code] = FinancialMetric(
                code=code,
                current_value=current_value,
                previous_value=previous_value,
                growth_rate=rate,
                change=current_value - (previous_value or ZERO),
                historical_baseline=baseline,
                baseline_delta=baseline_delta,
                sample_size=sample_size,
                data_coverage=coverage,
                quality_status=metric_quality,
                seasonality_adjusted=seasonality_adjusted,
            )
        return MetricSnapshot(
            customer_id=customer_id,
            as_of_date=as_of_date,
            window_days=window_days,
            metrics=metrics,
        )
