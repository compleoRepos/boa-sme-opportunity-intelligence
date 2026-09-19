from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import Query

from boa_oi.catalog import BOA_PRODUCTS, as_payload, demo_ownerships
from boa_oi.mock_data import (
    END_DATE,
    SECTORS,
    START_DATE,
    generate_balance_rows,
    generate_transaction_rows,
    scenario_for,
)
from boa_oi.platform import create_service_app
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "mock-banking-api",
    "Synthetic HTTP banking-system facade for integration tests and local demos.",
    database=False,
)
PREFIX = "/mock/v1"


def bounded(value: int) -> int:
    return min(max(value, 1), 500)


@app.get(f"{PREFIX}/customers", tags=["Mock Banking"])
def customers(
    customer_count: Annotated[int, Query(alias="customerCount", ge=1, le=500)] = 8,
) -> list[dict[str, Any]]:
    result = []
    for index in range(1, bounded(customer_count) + 1):
        ref = f"SME-{index:05d}"
        sector = SECTORS[(index - 1) % len(SECTORS)]
        result.append(
            {
                "customerId": ref,
                "legalName": f"Synthetic {sector.title()} Enterprise {index:05d}",
                "sector": sector,
                "segment": "SMALL" if index % 3 else "MEDIUM",
                "scenarioCode": scenario_for(index),
                "incorporatedOn": date(
                    2000 + index % 20, index % 12 + 1, index % 27 + 1
                ).isoformat(),
                "status": "ACTIVE",
                "relationshipManagerId": f"rm-{(index - 1) % 25 + 1:02d}",
                "relationshipManagerName": f"Synthetic RM {(index - 1) % 25 + 1:02d}",
                "branchId": f"BR-{((index - 1) % 25) // 5 + 1:02d}",
            }
        )
    return result


@app.get(f"{PREFIX}/accounts", tags=["Mock Banking"])
def accounts(
    customer_count: Annotated[int, Query(alias="customerCount", ge=1, le=500)] = 8,
) -> list[dict[str, Any]]:
    return [
        {
            "accountId": f"SYN-MA-{index:05d}-01",
            "customerId": f"SME-{index:05d}",
            "accountType": "CURRENT",
            "currency": "MAD",
            "openedAt": (START_DATE - timedelta(days=500)).isoformat(),
            "status": "ACTIVE",
        }
        for index in range(1, bounded(customer_count) + 1)
    ]


@app.get(f"{PREFIX}/balances", tags=["Mock Banking"])
def balances(
    customer_count: Annotated[int, Query(alias="customerCount", ge=1, le=500)] = 8,
) -> list[dict[str, Any]]:
    result = []
    for index in range(1, bounded(customer_count) + 1):
        account_ref = f"SYN-MA-{index:05d}-01"
        account_uuid = deterministic_uuid("account", f"SME-{index:05d}", 1)
        for row in generate_balance_rows(index, account_uuid):
            result.append(
                {
                    "accountId": account_ref,
                    "asOf": row["as_of_date"].isoformat(),
                    "ledger": float(row["closing_balance"]),
                    "available": float(row["available_balance"]),
                    "creditUsed": float(row["credit_used"]),
                    "creditLimit": float(row["credit_limit"]),
                    "currency": row["currency"],
                }
            )
    return result


@app.get(f"{PREFIX}/transactions", tags=["Mock Banking"])
def transactions(
    from_date: Annotated[date, Query(alias="fromDate")] = START_DATE,
    to_date: Annotated[date, Query(alias="toDate")] = END_DATE,
    customer_count: Annotated[int, Query(alias="customerCount", ge=1, le=500)] = 8,
) -> list[dict[str, Any]]:
    if from_date > to_date:
        return []
    result = []
    for index in range(1, bounded(customer_count) + 1):
        customer_ref = f"SME-{index:05d}"
        account_ref = f"SYN-MA-{index:05d}-01"
        customer_uuid = deterministic_uuid("customer", customer_ref)
        account_uuid = deterministic_uuid("account", customer_ref, 1)
        for row in generate_transaction_rows(index, customer_uuid, account_uuid):
            if from_date <= row["value_date"] <= to_date:
                result.append(
                    {
                        "transactionId": row["transaction_ref"],
                        "customerId": customer_ref,
                        "accountId": account_ref,
                        "bookingDate": row["booked_at"].isoformat(),
                        "valueDate": row["value_date"].isoformat(),
                        "type": row["transaction_type"],
                        "direction": row["direction"],
                        "amount": float(row["amount"]),
                        "currency": row["currency"],
                        "category": row["category"],
                        "international": row["is_international"],
                        "countryCode": row["country_code"],
                        "status": row["status"],
                        "sourceSystem": row["source_system"],
                    }
                )
    return result


@app.get(f"{PREFIX}/products", tags=["Mock Banking"])
def products(
    customer_count: Annotated[int, Query(alias="customerCount", ge=1, le=500)] = 8,
) -> dict[str, Any]:
    catalog = [as_payload(item) for item in BOA_PRODUCTS]
    ownerships = []
    for index in range(1, bounded(customer_count) + 1):
        ref = f"SME-{index:05d}"
        for code in demo_ownerships(ref, scenario_for(index)):
            ownerships.append(
                {
                    "customerId": ref,
                    "productId": code,
                    "status": "ACTIVE",
                    "openedOn": (START_DATE - timedelta(days=200)).isoformat(),
                    "utilizationRatio": 0.55,
                }
            )
    return {"products": catalog, "ownerships": ownerships}


@app.get(f"{PREFIX}/customers/{{customer_id}}/external-profile", tags=["Mock Banking"])
def external_profile(customer_id: str) -> dict[str, Any]:
    index = int(customer_id.split("-")[-1])
    return customers(index)[-1]


@app.get(f"{PREFIX}/customers/{{customer_id}}/international-flows", tags=["Mock Banking"])
def international_flows(customer_id: str) -> list[dict[str, Any]]:
    index = int(customer_id.split("-")[-1])
    return [
        row
        for row in transactions(START_DATE, END_DATE, index)
        if row["customerId"] == customer_id and row["international"]
    ]


@app.get(f"{PREFIX}/customers/{{customer_id}}/trade-finance-ownership", tags=["Mock Banking"])
def trade_finance_ownership(customer_id: str) -> dict[str, Any]:
    all_products = products(int(customer_id.split("-")[-1]))
    owned = next(
        (
            row
            for row in all_products["ownerships"]
            if row["customerId"] == customer_id and row["productId"] == "TRADE_FINANCE"
        ),
        None,
    )
    return {
        "customerId": customer_id,
        "productId": "TRADE_FINANCE",
        "status": "ABSENT" if owned is None else owned["status"],
    }


__all__ = ["app"]
