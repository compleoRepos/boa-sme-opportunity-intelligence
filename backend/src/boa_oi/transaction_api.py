from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.models.entities import Transaction, TransactionImportReceipt
from boa_oi.platform import (
    ADMIN_ROLES,
    READ_ROLES,
    Problem,
    correlation_id,
    create_service_app,
    decode_cursor,
    get_session,
    not_found,
    page_response,
    reject_unknown_filters,
    require_roles,
)
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "transaction-service",
    "Normalized transaction search and idempotent banking imports.",
)
PREFIX = "/internal/v1"


class TransactionIn(BaseModel):
    transactionId: str
    customerId: str
    accountId: str
    bookingDate: datetime
    valueDate: date
    type: str
    direction: str
    amount: Decimal = Field(gt=0)
    currency: str = "MAD"
    category: str
    international: bool = False
    countryCode: str = "MA"
    status: str = "BOOKED"
    sourceSystem: str = "BANKING_ADAPTER"


class TransactionBatch(BaseModel):
    sourceSystem: str
    externalBatchId: str
    transactions: list[TransactionIn] = Field(max_length=25_000)


def serialize(tx: Transaction) -> dict[str, Any]:
    return {
        "transactionId": tx.transaction_ref,
        "customerId": str(tx.customer_id),
        "accountId": str(tx.account_id),
        "bookingDate": tx.booked_at.isoformat(),
        "valueDate": tx.value_date.isoformat(),
        "type": tx.transaction_type,
        "direction": tx.direction,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "category": tx.category,
        "international": tx.is_international,
        "countryCode": tx.country_code,
        "sourceSystem": tx.source_system,
        "externalReference": tx.transaction_ref,
    }


def query_transactions(
    request: Request,
    session: Session,
    *,
    forced_customer: str | None = None,
    forced_account: str | None = None,
    page_size: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "customerId",
            "accountId",
            "fromDate",
            "toDate",
            "type",
            "direction",
            "currency",
            "category",
            "international",
            "minAmount",
            "maxAmount",
            "sort",
        },
    )
    params = request.query_params
    offset = decode_cursor(cursor)
    stmt = select(Transaction)
    customer_id = forced_customer or params.get("customerId")
    account_id = forced_account or params.get("accountId")
    if customer_id:
        stmt = stmt.where(Transaction.customer_id == deterministic_uuid("customer", customer_id))
    if account_id:
        stmt = stmt.where(Transaction.account_id == deterministic_uuid("account", account_id))
    if params.get("fromDate"):
        stmt = stmt.where(Transaction.value_date >= date.fromisoformat(params["fromDate"]))
    if params.get("toDate"):
        stmt = stmt.where(Transaction.value_date < date.fromisoformat(params["toDate"]))
    if params.get("type"):
        stmt = stmt.where(Transaction.transaction_type == params["type"])
    if params.get("direction"):
        stmt = stmt.where(Transaction.direction == params["direction"])
    if params.get("currency"):
        stmt = stmt.where(Transaction.currency == params["currency"])
    if params.get("category"):
        stmt = stmt.where(Transaction.category == params["category"])
    if params.get("international") is not None:
        stmt = stmt.where(
            Transaction.is_international == (params["international"].lower() == "true")
        )
    if params.get("minAmount"):
        stmt = stmt.where(Transaction.amount >= Decimal(params["minAmount"]))
    if params.get("maxAmount"):
        stmt = stmt.where(Transaction.amount <= Decimal(params["maxAmount"]))
    sort = params.get("sort", "-valueDate")
    column = {
        "valueDate": Transaction.value_date,
        "amount": Transaction.amount,
        "bookingDate": Transaction.booked_at,
    }.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported transaction sort field.")
    rows = list(
        session.scalars(
            stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), Transaction.id)
            .offset(offset)
            .limit(page_size + 1)
        )
    )
    return page_response(
        request,
        [serialize(row) for row in rows],
        page_size=page_size,
        offset=offset,
        total_count=None,
    )


@app.get(
    f"{PREFIX}/transactions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def list_transactions(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return query_transactions(request, session, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/transactions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def customer_transactions(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return query_transactions(
        request,
        session,
        forced_customer=customer_id,
        page_size=page_size,
        cursor=cursor,
    )


@app.get(
    f"{PREFIX}/accounts/{{account_id}}/transactions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def account_transactions(
    account_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return query_transactions(
        request, session, forced_account=account_id, page_size=page_size, cursor=cursor
    )


@app.get(
    f"{PREFIX}/transactions/{{transaction_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def get_transaction(transaction_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    tx = session.scalar(select(Transaction).where(Transaction.transaction_ref == transaction_id))
    if tx is None:
        raise not_found("Transaction")
    return serialize(tx)


@app.post(
    f"{PREFIX}/imports/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def import_transactions(
    batch: TransactionBatch,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    body_hash = hashlib.sha256(batch.model_dump_json().encode()).hexdigest()
    existing = session.scalar(
        select(TransactionImportReceipt).where(
            TransactionImportReceipt.idempotency_key == idempotency_key
        )
    )
    if existing:
        if existing.request_hash != body_hash:
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
    values = [
        {
            "id": deterministic_uuid("transaction", item.transactionId),
            "transaction_ref": item.transactionId,
            "customer_id": deterministic_uuid("customer", item.customerId),
            "account_id": deterministic_uuid("account", item.accountId),
            "booked_at": item.bookingDate,
            "value_date": item.valueDate,
            "direction": item.direction,
            "amount": item.amount,
            "currency": item.currency,
            "transaction_type": item.type,
            "category": item.category,
            "is_international": item.international,
            "country_code": item.countryCode,
            "status": item.status,
            "source_system": item.sourceSystem,
            "created_by": "banking-integration",
        }
        for item in batch.transactions
    ]
    chunk = 5_000
    for index in range(0, len(values), chunk):
        session.execute(
            pg_insert(Transaction)
            .values(values[index : index + chunk])
            .on_conflict_do_nothing(
                index_elements=[Transaction.source_system, Transaction.transaction_ref]
            )
        )
    record = TransactionImportReceipt(
        id=deterministic_uuid("import", "TRANSACTIONS", idempotency_key),
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        row_count=len(values),
        status="COMPLETED",
        correlation_id=correlation_id(request),
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    return {"jobId": str(record.id), "status": "COMPLETED", "imported": len(values)}


__all__ = ["app", "serialize"]
