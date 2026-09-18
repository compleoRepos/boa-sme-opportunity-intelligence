from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.models.entities import Account, AccountBalance, AccountImportReceipt
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
    "account-service", "Accounts, balances and credit-line utilization snapshots."
)
PREFIX = "/internal/v1"


class AccountIn(BaseModel):
    accountId: str
    customerId: str
    accountType: str
    currency: str = "MAD"
    openedAt: date
    status: str = "ACTIVE"


class BalanceIn(BaseModel):
    accountId: str
    asOf: date
    ledger: Decimal
    available: Decimal
    creditUsed: Decimal = Decimal(0)
    creditLimit: Decimal = Decimal(0)
    currency: str = "MAD"


class AccountBatch(BaseModel):
    externalBatchId: str
    accounts: list[AccountIn] = Field(max_length=10_000)
    balances: list[BalanceIn] = Field(default_factory=list, max_length=100_000)


def latest_balance(session: Session, account_id) -> AccountBalance | None:
    return session.scalar(
        select(AccountBalance)
        .where(AccountBalance.account_id == account_id)
        .order_by(AccountBalance.as_of_date.desc())
        .limit(1)
    )


def serialize(account: Account, balance: AccountBalance | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "accountId": account.account_ref,
        "customerId": str(account.customer_id),
        "accountType": account.account_type,
        "currency": account.currency,
        "status": account.status,
        "openedAt": account.opened_on.isoformat(),
    }
    if balance:
        payload["balance"] = {
            "asOf": balance.as_of_date.isoformat(),
            "available": float(balance.available_balance),
            "ledger": float(balance.closing_balance),
            "currency": balance.currency,
        }
        payload["creditLimit"] = float(balance.credit_limit)
    return payload


@app.get(
    f"{PREFIX}/accounts",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Accounts"],
)
def list_accounts(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    cursor: str | None = None,
    customer_id: Annotated[str | None, Query(alias="customerId")] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    currency: str | None = None,
    account_type: Annotated[str | None, Query(alias="accountType")] = None,
    sort: str = "accountId",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "customerId",
            "status",
            "currency",
            "accountType",
            "sort",
        },
    )
    offset = decode_cursor(cursor)
    stmt = select(Account)
    if customer_id:
        try:
            stmt = stmt.where(Account.customer_id == deterministic_uuid("customer", customer_id))
        except ValueError:
            stmt = stmt.where(Account.customer_id == customer_id)
    if status_filter:
        stmt = stmt.where(Account.status == status_filter)
    if currency:
        stmt = stmt.where(Account.currency == currency)
    if account_type:
        stmt = stmt.where(Account.account_type == account_type)
    column = {"accountId": Account.account_ref, "openedAt": Account.opened_on}.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported account sort field.")
    stmt = (
        stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), Account.id)
        .offset(offset)
        .limit(page_size + 1)
    )
    accounts = list(session.scalars(stmt))
    rows = [serialize(item, latest_balance(session, item.id)) for item in accounts]
    return page_response(
        request,
        rows,
        page_size=page_size,
        offset=offset,
        total_count=session.scalar(select(func.count()).select_from(Account)),
    )


@app.get(
    f"{PREFIX}/accounts/{{account_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Accounts"],
)
def get_account(account_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    account = session.scalar(select(Account).where(Account.account_ref == account_id))
    if account is None:
        raise not_found("Account")
    return serialize(account, latest_balance(session, account.id))


@app.get(
    f"{PREFIX}/accounts/{{account_id}}/balances",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Accounts"],
)
def list_balances(
    account_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 100,
    cursor: str | None = None,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
    period: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"pageSize", "cursor", "fromDate", "toDate", "period"})
    account = session.scalar(select(Account).where(Account.account_ref == account_id))
    if account is None:
        raise not_found("Account")
    offset = decode_cursor(cursor)
    stmt = select(AccountBalance).where(AccountBalance.account_id == account.id)
    if from_date:
        stmt = stmt.where(AccountBalance.as_of_date >= from_date)
    if to_date:
        stmt = stmt.where(AccountBalance.as_of_date < to_date)
    rows = list(
        session.scalars(
            stmt.order_by(AccountBalance.as_of_date.desc()).offset(offset).limit(page_size + 1)
        )
    )
    data = [
        {
            "accountId": account_id,
            "asOf": row.as_of_date.isoformat(),
            "ledger": float(row.closing_balance),
            "available": float(row.available_balance),
            "creditUsed": float(row.credit_used),
            "creditLimit": float(row.credit_limit),
            "currency": row.currency,
        }
        for row in rows
    ]
    return page_response(request, data, page_size=page_size, offset=offset, total_count=None)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/accounts",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Accounts"],
)
def customer_accounts(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 100,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"pageSize", "cursor", "sort"})
    offset = decode_cursor(cursor)
    customer_uuid = deterministic_uuid("customer", customer_id)
    accounts = list(
        session.scalars(
            select(Account)
            .where(Account.customer_id == customer_uuid)
            .order_by(Account.account_ref)
            .offset(offset)
            .limit(page_size + 1)
        )
    )
    data = []
    for item in accounts:
        row = serialize(item, latest_balance(session, item.id))
        row["customerId"] = customer_id
        data.append(row)
    return page_response(request, data, page_size=page_size, offset=offset, total_count=None)


@app.post(
    f"{PREFIX}/imports/accounts",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def import_accounts(
    batch: AccountBatch,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    existing = session.scalar(
        select(AccountImportReceipt).where(AccountImportReceipt.idempotency_key == idempotency_key)
    )
    body_hash = hashlib.sha256(batch.model_dump_json().encode()).hexdigest()
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
    for item in batch.accounts:
        session.execute(
            pg_insert(Account)
            .values(
                id=deterministic_uuid("account", item.accountId),
                account_ref=item.accountId,
                customer_id=deterministic_uuid("customer", item.customerId),
                account_type=item.accountType,
                currency=item.currency,
                opened_on=item.openedAt,
                status=item.status,
                created_by="banking-integration",
            )
            .on_conflict_do_update(
                index_elements=[Account.account_ref],
                set_={"status": item.status, "currency": item.currency},
            )
        )
    for row in batch.balances:
        session.execute(
            pg_insert(AccountBalance)
            .values(
                id=deterministic_uuid("balance", row.accountId, row.asOf),
                account_id=deterministic_uuid("account", row.accountId),
                as_of_date=row.asOf,
                closing_balance=row.ledger,
                available_balance=row.available,
                credit_used=row.creditUsed,
                credit_limit=row.creditLimit,
                currency=row.currency,
            )
            .on_conflict_do_update(
                index_elements=[AccountBalance.account_id, AccountBalance.as_of_date],
                set_={
                    "closing_balance": row.ledger,
                    "available_balance": row.available,
                    "credit_used": row.creditUsed,
                    "credit_limit": row.creditLimit,
                },
            )
        )
    record = AccountImportReceipt(
        id=deterministic_uuid("import", "ACCOUNTS", idempotency_key),
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        row_count=len(batch.accounts) + len(batch.balances),
        status="COMPLETED",
        correlation_id=correlation_id(request),
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    return {
        "jobId": str(record.id),
        "status": "COMPLETED",
        "imported": record.row_count,
    }


__all__ = ["app", "serialize"]
