from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.http_clients import HttpBankingAdapter, service_request
from boa_oi.models.entities import ImportBatch
from boa_oi.platform import (
    ADMIN_ROLES,
    Problem,
    correlation_id,
    create_service_app,
    get_session,
    require_roles,
)
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "banking-integration-service",
    "HTTP anti-corruption layer between banking adapters and domain services.",
)
PREFIX = "/internal/v1"


class ImportRequest(BaseModel):
    fromDate: date
    toDate: date
    customerCount: int = Field(default=8, ge=1, le=500)
    customerIds: list[str] | None = None
    source: str = "ALL"


def service_url(name: str) -> str:
    value = os.getenv(f"{name.upper()}_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{name.upper()}_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


@app.post(
    f"{PREFIX}/imports/all",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def import_all(
    payload: ImportRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    body_hash = payload.model_dump_json()
    existing = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_system == "BANKING_HTTP",
            ImportBatch.batch_ref == idempotency_key,
        )
    )
    if existing:
        if existing.input_hash != body_hash:
            raise Problem(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was reused with different content.",
            )
        return {
            "jobId": str(existing.id),
            "status": existing.status,
            "imported": existing.row_count,
        }
    corr = correlation_id(request)
    adapter = HttpBankingAdapter()
    customers = await adapter.fetch_customers(payload.customerCount, corr)
    accounts = await adapter.fetch_accounts(payload.customerCount, corr)
    balances = await adapter.fetch_balances(payload.customerCount, corr)
    transactions = await adapter.fetch_transactions(
        payload.fromDate, payload.toDate, payload.customerCount, corr
    )
    products = await adapter.fetch_products(payload.customerCount, corr)
    batch_id = f"banking-{idempotency_key}"
    responses = []
    responses.append(
        await service_request(
            "POST",
            f"{service_url('customer')}/internal/v1/imports/customers",
            correlation_id=corr,
            idempotency_key=f"{idempotency_key}-customers",
            json={
                "sourceSystem": "BANKING_HTTP",
                "externalBatchId": batch_id,
                "customers": customers,
            },
            timeout=30,
        )
    )
    responses.append(
        await service_request(
            "POST",
            f"{service_url('account')}/internal/v1/imports/accounts",
            correlation_id=corr,
            idempotency_key=f"{idempotency_key}-accounts",
            json={
                "externalBatchId": batch_id,
                "accounts": accounts,
                "balances": balances,
            },
            timeout=90,
        )
    )
    responses.append(
        await service_request(
            "POST",
            f"{service_url('transaction')}/internal/v1/imports/transactions",
            correlation_id=corr,
            idempotency_key=f"{idempotency_key}-transactions",
            json={
                "sourceSystem": "BANKING_HTTP",
                "externalBatchId": batch_id,
                "transactions": transactions,
            },
            timeout=120,
        )
    )
    responses.append(
        await service_request(
            "POST",
            f"{service_url('product')}/internal/v1/imports/products",
            correlation_id=corr,
            idempotency_key=f"{idempotency_key}-products",
            json={"externalBatchId": batch_id, **products},
            timeout=30,
        )
    )
    row_count = (
        len(customers)
        + len(accounts)
        + len(balances)
        + len(transactions)
        + len(products["ownerships"])
    )
    record = ImportBatch(
        id=deterministic_uuid("integration-import", idempotency_key),
        source_system="BANKING_HTTP",
        batch_ref=idempotency_key,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        input_hash=body_hash,
        row_count=row_count,
        status="COMPLETED",
        correlation_id=corr,
    )
    session.add(record)
    return {
        "jobId": str(record.id),
        "status": "COMPLETED",
        "imported": row_count,
        "services": responses,
    }


@app.post(
    f"{PREFIX}/imports/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def import_transactions(
    payload: ImportRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> dict[str, Any]:
    corr = correlation_id(request)
    rows = await HttpBankingAdapter().fetch_transactions(
        payload.fromDate, payload.toDate, payload.customerCount, corr
    )
    return await service_request(
        "POST",
        f"{service_url('transaction')}/internal/v1/imports/transactions",
        correlation_id=corr,
        idempotency_key=idempotency_key,
        json={
            "sourceSystem": "BANKING_HTTP",
            "externalBatchId": idempotency_key,
            "transactions": rows,
        },
        timeout=120,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/external-profile",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def external_profile(customer_id: str, request: Request) -> dict[str, Any]:
    adapter = HttpBankingAdapter()
    return await service_request(
        "GET",
        f"{adapter.base_url}/mock/v1/customers/{customer_id}/external-profile",
        correlation_id=correlation_id(request),
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/international-flows",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def external_flows(customer_id: str, request: Request) -> list[dict[str, Any]]:
    adapter = HttpBankingAdapter()
    return await service_request(
        "GET",
        f"{adapter.base_url}/mock/v1/customers/{customer_id}/international-flows",
        correlation_id=correlation_id(request),
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/trade-finance-ownership",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def trade_ownership(customer_id: str, request: Request) -> dict[str, Any]:
    adapter = HttpBankingAdapter()
    return await service_request(
        "GET",
        f"{adapter.base_url}/mock/v1/customers/{customer_id}/trade-finance-ownership",
        correlation_id=correlation_id(request),
    )


__all__ = ["app"]
