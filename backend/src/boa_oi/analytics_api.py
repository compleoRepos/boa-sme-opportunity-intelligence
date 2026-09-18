from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.analytics.domain import BalanceFact, MetricSnapshot, TransactionFact
from boa_oi.analytics.service import SUPPORTED_WINDOWS, AnalyticsEngine
from boa_oi.http_clients import service_request
from boa_oi.models.entities import MetricSnapshot as MetricSnapshotRecord
from boa_oi.platform import (
    ANALYTICS_ROLES,
    READ_ROLES,
    Problem,
    correlation_id,
    create_service_app,
    decode_cursor,
    get_session,
    page_response,
    reject_unknown_filters,
    require_roles,
)
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "analytics-service", "Persisted financial metrics for 7/30/90/180/365-day windows."
)
PREFIX = "/internal/v1"
CALCULATION_VERSION = "analytics-0.1.0"


class RecomputeRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    asOf: date
    periods: list[str] = Field(default_factory=lambda: ["7D", "30D", "90D", "180D", "365D"])


def dependency_url(name: str) -> str:
    value = os.getenv(f"{name.upper()}_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{name.upper()}_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def metric_rows(snapshot: MetricSnapshot) -> list[dict[str, Any]]:
    result = []
    for code, metric in sorted(snapshot.metrics.items()):
        result.append(
            {
                "customerId": str(snapshot.customer_id),
                "metric": code,
                "currentValue": float(metric.current_value),
                "previousPeriodValue": float(metric.previous_value)
                if metric.previous_value is not None
                else None,
                "historicalBaselineValue": float(metric.historical_baseline)
                if metric.historical_baseline is not None
                else None,
                "growthRate": float(metric.growth_rate) if metric.growth_rate is not None else None,
                "deviationFromBaseline": float(metric.baseline_delta)
                if metric.baseline_delta is not None
                else None,
                "change": float(metric.change) if metric.change is not None else None,
                "period": f"{snapshot.window_days}D",
                "asOf": snapshot.as_of_date.isoformat(),
                "currency": "MAD",
                "calculationVersion": CALCULATION_VERSION,
                "dataQuality": metric.quality_status,
                "dataCoverage": float(metric.data_coverage),
                "sampleSize": metric.sample_size,
                "seasonalityAdjusted": metric.seasonality_adjusted,
            }
        )
    return result


def persisted_rows(
    session: Session,
    *,
    customer_id: str | None = None,
    period: str | None = None,
    metric: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(MetricSnapshotRecord)
    if customer_id:
        stmt = stmt.where(
            MetricSnapshotRecord.customer_id == deterministic_uuid("customer", customer_id)
        )
    if period:
        stmt = stmt.where(MetricSnapshotRecord.window_days == int(period.removesuffix("D")))
    snapshots = list(
        session.scalars(
            stmt.order_by(MetricSnapshotRecord.as_of_date.desc(), MetricSnapshotRecord.window_days)
        )
    )
    rows = []
    for snap in snapshots:
        payload = snap.values_json
        for code, item in payload.items():
            if metric and code != metric:
                continue
            rows.append(
                {
                    "customerId": str(snap.customer_id),
                    "metric": code,
                    "currentValue": item.get("currentValue"),
                    "previousPeriodValue": item.get("previousPeriodValue"),
                    "historicalBaselineValue": item.get("historicalBaselineValue"),
                    "growthRate": item.get("growthRate"),
                    "deviationFromBaseline": item.get("deviationFromBaseline"),
                    "change": item.get("change"),
                    "period": f"{snap.window_days}D",
                    "asOf": snap.as_of_date.isoformat(),
                    "currency": "MAD",
                    "calculationVersion": snap.calculation_version,
                    "dataQuality": item.get("dataQuality"),
                    "dataCoverage": item.get("dataCoverage"),
                    "sampleSize": item.get("sampleSize"),
                    "seasonalityAdjusted": item.get("seasonalityAdjusted"),
                }
            )
    return rows


@app.get(
    f"{PREFIX}/metrics",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Analytics"],
)
def list_metrics(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    customer_id: Annotated[str | None, Query(alias="customerId")] = None,
    metric: str | None = None,
    period: str | None = None,
    sort: str = "-asOf",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "customerId",
            "metric",
            "period",
            "fromDate",
            "toDate",
            "sort",
        },
    )
    offset = decode_cursor(cursor)
    rows = persisted_rows(session, customer_id=customer_id, period=period, metric=metric)
    return page_response(
        request,
        rows[offset : offset + page_size + 1],
        page_size=page_size,
        offset=offset,
        total_count=len(rows),
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/metrics",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Analytics"],
)
def customer_metrics(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 100,
    cursor: str | None = None,
    metric: str | None = None,
    period: str | None = None,
    sort: str = "-asOf",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"pageSize", "cursor", "metric", "period", "sort"})
    offset = decode_cursor(cursor)
    rows = persisted_rows(session, customer_id=customer_id, period=period, metric=metric)
    return page_response(
        request,
        rows[offset : offset + page_size + 1],
        page_size=page_size,
        offset=offset,
        total_count=len(rows),
    )


async def recompute_one(
    customer_id: str,
    as_of: date,
    periods: list[str],
    request: Request,
    session: Session,
) -> int:
    corr = correlation_id(request)
    auth = request.headers.get("Authorization")
    transaction_rows: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params = {
            "fromDate": (as_of - timedelta(days=730)).isoformat(),
            "toDate": (as_of + timedelta(days=1)).isoformat(),
            "pageSize": 1000,
            "sort": "valueDate",
        }
        if cursor:
            params["cursor"] = cursor
        tx_page = await service_request(
            "GET",
            f"{dependency_url('transaction')}/internal/v1/customers/{customer_id}/transactions",
            correlation_id=corr,
            params=params,
            incoming_authorization=auth,
        )
        transaction_rows.extend(tx_page["data"])
        cursor = tx_page.get("meta", {}).get("nextCursor")
        if not cursor:
            break
    account_page = await service_request(
        "GET",
        f"{dependency_url('account')}/internal/v1/customers/{customer_id}/accounts",
        correlation_id=corr,
        params={"pageSize": 100},
        incoming_authorization=auth,
    )
    transactions = [
        TransactionFact(
            transaction_ref=row["transactionId"],
            customer_id=customer_id,
            account_id=row["accountId"],
            value_date=date.fromisoformat(row["valueDate"]),
            direction=row["direction"],
            amount=Decimal(str(row["amount"])),
            category=row.get("category") or "OTHER",
            is_international=bool(row.get("international")),
            status="BOOKED",
            is_internal_transfer=False,
        )
        for row in transaction_rows
    ]
    balances: list[BalanceFact] = []
    for account in account_page["data"]:
        balance_page = await service_request(
            "GET",
            f"{dependency_url('account')}/internal/v1/accounts/{account['accountId']}/balances",
            correlation_id=corr,
            params={
                "fromDate": (as_of - timedelta(days=730)).isoformat(),
                "toDate": (as_of + timedelta(days=1)).isoformat(),
                "pageSize": 1000,
            },
            incoming_authorization=auth,
        )
        balances.extend(
            BalanceFact(
                account_id=account["accountId"],
                as_of_date=date.fromisoformat(row["asOf"]),
                closing_balance=Decimal(str(row["ledger"])),
                credit_limit=Decimal(str(row.get("creditLimit", 0))),
                credit_used=Decimal(str(row.get("creditUsed", 0))),
            )
            for row in balance_page["data"]
        )
    engine = AnalyticsEngine()
    count = 0
    for period in periods:
        days = int(period.removesuffix("D"))
        if days not in SUPPORTED_WINDOWS:
            raise Problem(422, "VALIDATION_ERROR", f"Unsupported analytics period: {period}")
        history: dict[str, list[Decimal]] = defaultdict(list)
        available_days = max(
            0,
            (as_of - min((item.value_date for item in transactions), default=as_of)).days + 1,
        )
        historical_windows = min(11, max(0, available_days // days - 1))
        for window_index in range(1, historical_windows + 1):
            historical_as_of = as_of - timedelta(days=days * window_index)
            historical_snapshot = engine.calculate(
                customer_id, transactions, balances, historical_as_of, days
            )
            for code, metric in historical_snapshot.metrics.items():
                history[code].append(metric.current_value)
        snapshot = engine.calculate(
            customer_id,
            transactions,
            balances,
            as_of,
            days,
            historical_values=dict(history),
        )
        values = {row["metric"]: row for row in metric_rows(snapshot)}
        session.execute(
            pg_insert(MetricSnapshotRecord)
            .values(
                id=deterministic_uuid(
                    "metric-snapshot", customer_id, as_of, days, CALCULATION_VERSION
                ),
                customer_id=deterministic_uuid("customer", customer_id),
                as_of_date=as_of,
                window_days=days,
                calculation_version=CALCULATION_VERSION,
                values_json=values,
                input_watermark=f"{len(transactions)}tx/{len(balances)}balances",
                created_by="analytics-service",
            )
            .on_conflict_do_update(
                index_elements=[
                    MetricSnapshotRecord.customer_id,
                    MetricSnapshotRecord.as_of_date,
                    MetricSnapshotRecord.window_days,
                    MetricSnapshotRecord.calculation_version,
                ],
                set_={
                    "values_json": values,
                    "input_watermark": f"{len(transactions)}tx/{len(balances)}balances",
                },
            )
        )
        count += len(values)
    return count


@app.post(
    f"{PREFIX}/analytics/recompute",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Analytics"],
)
async def recompute(
    payload: RecomputeRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    calculated = 0
    for customer_id in payload.customerIds:
        calculated += await recompute_one(
            customer_id, payload.asOf, payload.periods, request, session
        )
    return {
        "jobId": str(deterministic_uuid("analytics-job", idempotency_key)),
        "status": "COMPLETED",
        "customers": len(payload.customerIds),
        "metrics": calculated,
        "asOf": payload.asOf.isoformat(),
    }


@app.post(
    f"{PREFIX}/customers/{{customer_id}}/metrics/recalculate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Analytics"],
)
async def recalculate_customer(
    customer_id: str,
    payload: RecomputeRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    payload.customerIds = [customer_id]
    return await recompute(payload, request, idempotency_key, session)


@app.get(
    f"{PREFIX}/health/data-freshness",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Analytics"],
)
def freshness(session: Session = Depends(get_session)) -> dict[str, Any]:
    latest = session.scalar(select(func.max(MetricSnapshotRecord.as_of_date)))
    return {
        "latestAsOf": latest.isoformat() if latest else None,
        "calculationVersion": CALCULATION_VERSION,
        "status": "FRESH" if latest else "EMPTY",
    }


__all__ = ["app"]
