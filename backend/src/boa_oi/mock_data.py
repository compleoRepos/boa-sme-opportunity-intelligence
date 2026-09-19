from __future__ import annotations

import hashlib
import random
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from boa_oi.catalog import PRODUCTS, PRODUCTS_BY_FAMILY  # noqa: F401

START_DATE = date(2025, 10, 1)
END_DATE = date(2026, 9, 30)
SEED = "boa-sme-oi-2026-v1"
SECTORS = (
    "INDUSTRIE",
    "IMPORT_EXPORT",
    "DISTRIBUTION",
    "SERVICES",
    "BTP",
    "AGRICULTURE",
    "COMMERCE",
    "TECHNOLOGIE",
)
SCENARIOS = (
    "GROWTH_COMPANY",
    "STABLE_COMPANY",
    "INTERNATIONAL_GROWTH",
    "CASH_SURPLUS",
    "FINANCIAL_STRESS",
    "NORMAL_CUSTOMER",
    "FALSE_POSITIVE_SEASONAL",
    "FALSE_POSITIVE_ONE_OFF",
)


def rng_for(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, (SEED, *parts))).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def scenario_for(index: int) -> str:
    return SCENARIOS[(index - 1) % len(SCENARIOS)]


def monthly_multiplier(scenario: str, month_index: int, sector: str) -> float:
    recent = month_index >= 9
    base = 1.0
    if scenario == "GROWTH_COMPANY" and recent:
        base = 1.42
    elif scenario == "INTERNATIONAL_GROWTH" and recent:
        base = 1.50
    elif scenario == "FINANCIAL_STRESS" and recent:
        base = 0.65
    elif scenario == "FALSE_POSITIVE_SEASONAL" and month_index == 2:
        base = 1.65
    if sector in {"COMMERCE", "DISTRIBUTION"} and month_index == 2:
        base *= 1.15
    if sector == "AGRICULTURE" and month_index in {5, 6}:
        base *= 1.25
    return base


def generate_transaction_rows(
    customer_index: int, customer_id: UUID, account_id: UUID
) -> Iterator[dict]:
    customer_ref = f"SME-{customer_index:05d}"
    scenario = scenario_for(customer_index)
    sector = SECTORS[(customer_index - 1) % len(SECTORS)]
    rng = rng_for(customer_ref, "transactions")
    current = START_DATE
    sequence = 0
    while current <= END_DATE:
        month_index = (current.year - START_DATE.year) * 12 + current.month - START_DATE.month
        mult = monthly_multiplier(scenario, month_index, sector)
        daily_count = 2 if current.weekday() < 5 else 1
        if sector in {"COMMERCE", "DISTRIBUTION"}:
            daily_count += 1
        if scenario == "GROWTH_COMPANY" and month_index >= 9:
            daily_count += 1
        for item_no in range(daily_count):
            sequence += 1
            is_credit = item_no == 0 or rng.random() < 0.38
            direction = "CREDIT" if is_credit else "DEBIT"
            category = (
                "CUSTOMER_RECEIPT"
                if is_credit
                else (
                    "SUPPLIER_PAYMENT"
                    if rng.random() < (0.65 if sector in {"INDUSTRIE", "BTP"} else 0.40)
                    else "OPERATING_EXPENSE"
                )
            )
            international_base = 0.20 if sector == "IMPORT_EXPORT" else 0.015
            international = rng.random() < international_base
            if scenario == "INTERNATIONAL_GROWTH" and month_index >= 9:
                international = rng.random() < 0.48
            if scenario == "FALSE_POSITIVE_ONE_OFF":
                international = current == date(2026, 8, 17) and item_no == 0
            amount_base = 26000.0 if is_credit else 16500.0
            if category == "SUPPLIER_PAYMENT" and scenario == "GROWTH_COMPANY" and month_index >= 9:
                amount_base *= 1.32
            amount = Decimal(str(round(max(100, amount_base * mult * rng.uniform(0.65, 1.35)), 2)))
            if scenario == "FALSE_POSITIVE_ONE_OFF" and international:
                amount = Decimal("1750000.00")
            tx_ref = f"TX-{customer_index:05d}-{current:%Y%m%d}-{item_no:02d}"
            yield {
                "transaction_ref": tx_ref,
                "customer_id": customer_id,
                "account_id": account_id,
                "booked_at": datetime.combine(current, time(12), tzinfo=timezone.utc),
                "value_date": current,
                "direction": direction,
                "amount": amount,
                "currency": "MAD",
                "transaction_type": "TRANSFER" if international else "PAYMENT",
                "category": category,
                "is_international": international,
                "country_code": "FR" if international else "MA",
                "status": "BOOKED",
                "source_system": "MOCK_PAYMENTS",
            }
        current += timedelta(days=1)


def generate_balance_rows(customer_index: int, account_id: UUID) -> Iterator[dict]:
    scenario = scenario_for(customer_index)
    rng = rng_for(customer_index, "balances")
    balance = (
        Decimal(1800000)
        if scenario == "CASH_SURPLUS"
        else Decimal(str(250000 + customer_index * 500))
    )
    current = START_DATE
    while current <= END_DATE:
        progress = Decimal((current - START_DATE).days) / Decimal((END_DATE - START_DATE).days)
        if scenario == "FINANCIAL_STRESS":
            balance -= Decimal(600) if current < date(2026, 7, 1) else Decimal(2600)
        elif scenario == "CASH_SURPLUS":
            balance += Decimal(str(rng.randint(-2500, 3500)))
        else:
            balance += Decimal(str(rng.randint(-6000, 6500)))
        limit = Decimal(1000000)
        used = (
            (
                Decimal(150000)
                if current < date(2026, 7, 1)
                else Decimal(650000) + Decimal(250000) * progress
            )
            if scenario == "FINANCIAL_STRESS"
            else Decimal(100000)
        )
        yield {
            "account_id": account_id,
            "as_of_date": current,
            "closing_balance": balance,
            "available_balance": balance + limit - used,
            "credit_used": used,
            "credit_limit": limit,
            "currency": "MAD",
        }
        current += timedelta(days=1)
