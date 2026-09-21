from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.analytics.domain import BalanceFact, MetricSnapshot, TransactionFact
from boa_oi.analytics.service import SUPPORTED_WINDOWS, AnalyticsEngine
from boa_oi.http_clients import service_request
from boa_oi.models.entities import FlowVisibilityPolicy, ImportBatch
from boa_oi.models.entities import FlowVisibilitySnapshot as FlowVisibilitySnapshotRecord
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
from boa_oi.visibility import VisibilityTransaction, estimate_flow_visibility

app = create_service_app(
    "analytics-service", "Persisted financial metrics for 7/30/90/180/365-day windows."
)
PREFIX = "/internal/v1"
CALCULATION_VERSION = "analytics-0.1.0"
CHECKPOINT_SOURCE = "ANALYTICS_CHECKPOINT"


@dataclass(frozen=True)
class AnalyticsInputs:
    transactions: tuple[TransactionFact, ...]
    balances: tuple[BalanceFact, ...]
    customer: dict[str, Any] | None = None


class RecomputeRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    asOf: date
    periods: list[str] = Field(default_factory=lambda: ["7D", "30D", "90D", "180D", "365D"])
    mode: Literal["INCREMENTAL", "HISTORICAL"] = "INCREMENTAL"
    checkpointScope: Literal["CUSTOMER", "BATCH"] = "CUSTOMER"
    checkpointKey: str | None = Field(default=None, min_length=1, max_length=200)


class RecomputeResponse(BaseModel):
    jobId: str
    status: Literal["COMPLETED"]
    customers: int
    processed: int
    skipped: int
    metrics: int
    asOf: date
    mode: Literal["INCREMENTAL", "HISTORICAL"]
    checkpointScope: Literal["CUSTOMER", "BATCH"]
    lastEvaluatedAt: datetime


def dependency_url(name: str) -> str:
    value = os.getenv(f"{name.upper()}_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{name.upper()}_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def analytics_input_hash(
    inputs: AnalyticsInputs,
    *,
    as_of: date,
    periods: list[str],
    visibility_policy: dict[str, Any] | None = None,
) -> str:
    transactions = sorted(
        (
            {
                "transactionRef": item.transaction_ref,
                "customerId": item.customer_id,
                "accountId": item.account_id,
                "valueDate": item.value_date.isoformat(),
                "direction": item.direction,
                "amount": str(item.amount),
                "category": item.category,
                "international": item.is_international,
                "status": item.status,
                "internalTransfer": item.is_internal_transfer,
            }
            for item in inputs.transactions
        ),
        key=lambda item: json.dumps(item, sort_keys=True),
    )
    balances = sorted(
        (
            {
                "accountId": item.account_id,
                "asOf": item.as_of_date.isoformat(),
                "closingBalance": str(item.closing_balance),
                "creditLimit": str(item.credit_limit),
                "creditUsed": str(item.credit_used),
            }
            for item in inputs.balances
        ),
        key=lambda item: json.dumps(item, sort_keys=True),
    )
    return _canonical_hash(
        {
            "asOf": as_of.isoformat(),
            "calculationVersion": CALCULATION_VERSION,
            "visibilityPolicy": visibility_policy or {},
            "periods": sorted(periods),
            "transactions": transactions,
            "balances": balances,
            "customer": inputs.customer or {},
        }
    )


def checkpoint_ref(
    scope: Literal["CUSTOMER", "BATCH"],
    *,
    customer_ids: list[str],
    checkpoint_key: str | None,
) -> str:
    identity: dict[str, Any] = {"scope": scope}
    if checkpoint_key:
        identity["key"] = checkpoint_key
    if scope == "CUSTOMER":
        identity["customerId"] = customer_ids[0]
    else:
        identity["customerIds"] = sorted(customer_ids)
    return f"analytics-{scope.lower()}-{_canonical_hash(identity)[:64]}"


def find_checkpoint(session: Session, batch_ref: str) -> ImportBatch | None:
    return session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_system == CHECKPOINT_SOURCE,
            ImportBatch.batch_ref == batch_ref,
        )
    )


def save_checkpoint(
    session: Session,
    *,
    batch_ref: str,
    input_hash: str,
    row_count: int,
    request: Request,
    evaluated_at: datetime,
    existing: ImportBatch | None,
) -> ImportBatch:
    if existing is None:
        existing = ImportBatch(
            id=deterministic_uuid("analytics-checkpoint", batch_ref),
            source_system=CHECKPOINT_SOURCE,
            batch_ref=batch_ref,
            started_at=evaluated_at,
            completed_at=evaluated_at,
            input_hash=input_hash,
            row_count=row_count,
            status="COMPLETED",
            correlation_id=correlation_id(request),
        )
        session.add(existing)
        return existing
    existing.started_at = evaluated_at
    existing.completed_at = evaluated_at
    existing.input_hash = input_hash
    existing.row_count = row_count
    existing.status = "COMPLETED"
    existing.correlation_id = correlation_id(request)
    return existing


def observed_history(
    transactions: tuple[TransactionFact, ...], as_of: date
) -> tuple[int, date | None]:
    observed_from = min(
        (item.value_date for item in transactions if item.value_date <= as_of),
        default=None,
    )
    history_days = (as_of - observed_from).days + 1 if observed_from is not None else 0
    return history_days, observed_from


def metric_rows(
    snapshot: MetricSnapshot,
    *,
    history_days: int,
    observed_from: date | None,
) -> list[dict[str, Any]]:
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
                "historyDays": history_days,
                "observedFrom": observed_from.isoformat() if observed_from is not None else None,
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
                    "historyDays": item.get("historyDays"),
                    "observedFrom": item.get("observedFrom"),
                }
            )
    return rows


def parse_date_filter(request: Request, name: str) -> date | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            f"{name} must be a valid ISO date (YYYY-MM-DD).",
            details=[
                {
                    "field": name,
                    "code": "date_from_datetime_parsing",
                    "message": f"Invalid date: {raw}",
                }
            ],
        ) from exc


def filter_metric_dates(rows: list[dict[str, Any]], request: Request) -> list[dict[str, Any]]:
    from_date = parse_date_filter(request, "fromDate")
    to_date = parse_date_filter(request, "toDate")
    if from_date is not None and to_date is not None and to_date <= from_date:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            "toDate must be after fromDate.",
            details=[
                {
                    "field": "toDate",
                    "code": "date_range",
                    "message": "toDate must be after fromDate.",
                }
            ],
        )
    return [
        row
        for row in rows
        if (from_date is None or date.fromisoformat(str(row["asOf"])) >= from_date)
        and (to_date is None or date.fromisoformat(str(row["asOf"])) < to_date)
    ]


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
    rows = filter_metric_dates(
        persisted_rows(session, customer_id=customer_id, period=period, metric=metric), request
    )
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
    reject_unknown_filters(
        request, {"pageSize", "cursor", "metric", "period", "fromDate", "toDate", "sort"}
    )
    offset = decode_cursor(cursor)
    rows = filter_metric_dates(
        persisted_rows(session, customer_id=customer_id, period=period, metric=metric), request
    )
    return page_response(
        request,
        rows[offset : offset + page_size + 1],
        page_size=page_size,
        offset=offset,
        total_count=len(rows),
    )


def validate_periods(periods: list[str]) -> None:
    for period in periods:
        try:
            days = int(period.removesuffix("D"))
        except ValueError as exc:
            raise Problem(
                422, "VALIDATION_ERROR", f"Unsupported analytics period: {period}"
            ) from exc
        if not period.endswith("D") or days not in SUPPORTED_WINDOWS:
            raise Problem(422, "VALIDATION_ERROR", f"Unsupported analytics period: {period}")


async def load_analytics_inputs(
    customer_id: str,
    as_of: date,
    request: Request,
) -> AnalyticsInputs:
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
    customer = await service_request(
        "GET",
        f"{dependency_url('customer')}/internal/v1/customers/{customer_id}",
        correlation_id=corr,
        params={"asOf": as_of.isoformat()},
        incoming_authorization=auth,
    )
    transactions = tuple(
        TransactionFact(
            transaction_ref=row["transactionId"],
            customer_id=customer_id,
            account_id=row["accountId"],
            value_date=date.fromisoformat(row["valueDate"]),
            direction=row["direction"],
            amount=Decimal(str(row["amount"])),
            category=row.get("category") or "OTHER",
            is_international=bool(row.get("international")),
            status=row.get("status") or "BOOKED",
            is_internal_transfer=False,
        )
        for row in transaction_rows
    )
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
    return AnalyticsInputs(
        transactions=transactions,
        balances=tuple(balances),
        customer={**customer, "transactionRows": transaction_rows},
    )


def active_visibility_policy(session: Session) -> tuple[int | None, dict[str, Any]]:
    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not inspect(bind).has_table(
        FlowVisibilityPolicy.__tablename__, schema="analytics"
    ):
        return None, {}
    row = session.scalar(
        select(FlowVisibilityPolicy)
        .where(FlowVisibilityPolicy.active.is_(True))
        .order_by(FlowVisibilityPolicy.version.desc())
        .limit(1)
    )
    return (row.version, dict(row.configuration_json)) if row is not None else (None, {})


def persist_flow_visibility(
    customer_id: str,
    as_of: date,
    inputs: AnalyticsInputs,
    input_hash: str,
    session: Session,
) -> None:
    customer = inputs.customer or {}
    rows = customer.get("transactionRows", [])
    declaration = customer.get("bankingRelationshipDeclaration") or {}
    policy_version, policy = active_visibility_policy(session)
    estimate = estimate_flow_visibility(
        as_of=as_of,
        banking_relationship=customer.get("bankingRelationship"),
        relationship_as_of=(
            datetime.fromisoformat(declaration["declaredAt"])
            if declaration.get("declaredAt")
            else None
        ),
        declared_turnover=(
            Decimal(str(customer["declaredTurnover"]))
            if customer.get("declaredTurnover") is not None
            else None
        ),
        turnover_as_of=(
            date.fromisoformat(customer["declaredTurnoverAsOf"])
            if customer.get("declaredTurnoverAsOf")
            else None
        ),
        transactions=(
            VisibilityTransaction(
                value_date=date.fromisoformat(row["valueDate"]),
                direction=row["direction"],
                amount=Decimal(str(row["amount"])),
                category=row.get("category") or "OTHER",
                status=row.get("status") or "BOOKED",
            )
            for row in rows
        ),
        high_share=float(policy.get("highShare", 0.70)),
        partial_share=float(policy.get("partialShare", 0.30)),
        fingerprint_threshold=int(policy.get("fingerprints90d", 2)),
    )
    calculation_version = (
        f"{CALCULATION_VERSION}+visibility-policy-v{policy_version}"
        if policy_version is not None
        else f"{CALCULATION_VERSION}+visibility-policy-default"
    )
    session.execute(
        pg_insert(FlowVisibilitySnapshotRecord)
        .values(
            id=deterministic_uuid("flow-visibility", customer_id, as_of, calculation_version),
            customer_id=deterministic_uuid("customer", customer_id),
            customer_ref=customer_id,
            as_of_date=as_of,
            level=estimate.level,
            estimated_share=estimate.estimated_share,
            method=estimate.method,
            evidence_json=list(estimate.evidence),
            fingerprint_count_90d=estimate.fingerprint_count_90d,
            fingerprint_previous_90d=estimate.fingerprint_previous_90d,
            categorization_coverage=estimate.categorization_coverage,
            calculation_version=calculation_version,
            input_watermark=input_hash,
            created_by="analytics-service",
        )
        .on_conflict_do_update(
            index_elements=[
                FlowVisibilitySnapshotRecord.customer_id,
                FlowVisibilitySnapshotRecord.as_of_date,
                FlowVisibilitySnapshotRecord.calculation_version,
            ],
            set_={
                "level": estimate.level,
                "estimated_share": estimate.estimated_share,
                "method": estimate.method,
                "evidence_json": list(estimate.evidence),
                "fingerprint_count_90d": estimate.fingerprint_count_90d,
                "fingerprint_previous_90d": estimate.fingerprint_previous_90d,
                "categorization_coverage": estimate.categorization_coverage,
                "input_watermark": input_hash,
            },
        )
    )


def persist_analytics_metrics(
    customer_id: str,
    as_of: date,
    periods: list[str],
    inputs: AnalyticsInputs,
    input_hash: str,
    session: Session,
) -> int:
    engine = AnalyticsEngine()
    count = 0
    persist_flow_visibility(customer_id, as_of, inputs, input_hash, session)
    history_days, observed_from = observed_history(inputs.transactions, as_of)
    for period in periods:
        days = int(period.removesuffix("D"))
        history: dict[str, list[Decimal]] = defaultdict(list)
        available_days = max(
            0,
            (as_of - min((item.value_date for item in inputs.transactions), default=as_of)).days
            + 1,
        )
        historical_windows = min(11, max(0, available_days // days - 1))
        for window_index in range(1, historical_windows + 1):
            historical_as_of = as_of - timedelta(days=days * window_index)
            historical_snapshot = engine.calculate(
                customer_id,
                list(inputs.transactions),
                list(inputs.balances),
                historical_as_of,
                days,
            )
            for code, metric in historical_snapshot.metrics.items():
                history[code].append(metric.current_value)
        snapshot = engine.calculate(
            customer_id,
            list(inputs.transactions),
            list(inputs.balances),
            as_of,
            days,
            historical_values=dict(history),
        )
        values = {
            row["metric"]: row
            for row in metric_rows(
                snapshot,
                history_days=history_days,
                observed_from=observed_from,
            )
        }
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
                input_watermark=input_hash,
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
                    "input_watermark": input_hash,
                },
            )
        )
        count += len(values)
    return count


async def recompute_one(
    customer_id: str,
    as_of: date,
    periods: list[str],
    request: Request,
    session: Session,
) -> int:
    validate_periods(periods)
    inputs = await load_analytics_inputs(customer_id, as_of, request)
    policy_version, policy = active_visibility_policy(session)
    input_hash = analytics_input_hash(
        inputs,
        as_of=as_of,
        periods=periods,
        visibility_policy={"version": policy_version, **policy},
    )
    return persist_analytics_metrics(customer_id, as_of, periods, inputs, input_hash, session)


async def incremental_by_customer(
    payload: RecomputeRequest,
    request: Request,
    session: Session,
) -> tuple[int, int, int, datetime]:
    processed = 0
    skipped = 0
    calculated = 0
    evaluated_at = datetime.now(timezone.utc)
    for customer_id in payload.customerIds:
        inputs = await load_analytics_inputs(customer_id, payload.asOf, request)
        policy_version, policy = active_visibility_policy(session)
        input_hash = analytics_input_hash(
            inputs,
            as_of=payload.asOf,
            periods=payload.periods,
            visibility_policy={"version": policy_version, **policy},
        )
        ref = checkpoint_ref(
            "CUSTOMER",
            customer_ids=[customer_id],
            checkpoint_key=payload.checkpointKey,
        )
        existing = find_checkpoint(session, ref)
        if existing is not None and existing.input_hash == input_hash:
            skipped += 1
            row_count = existing.row_count
        else:
            row_count = persist_analytics_metrics(
                customer_id,
                payload.asOf,
                payload.periods,
                inputs,
                input_hash,
                session,
            )
            calculated += row_count
            processed += 1
        save_checkpoint(
            session,
            batch_ref=ref,
            input_hash=input_hash,
            row_count=row_count,
            request=request,
            evaluated_at=evaluated_at,
            existing=existing,
        )
    return processed, skipped, calculated, evaluated_at


async def incremental_by_batch(
    payload: RecomputeRequest,
    request: Request,
    session: Session,
) -> tuple[int, int, int, datetime]:
    evaluated_at = datetime.now(timezone.utc)
    inputs_by_customer = {
        customer_id: await load_analytics_inputs(customer_id, payload.asOf, request)
        for customer_id in payload.customerIds
    }
    policy_version, policy = active_visibility_policy(session)
    hashes = {
        customer_id: analytics_input_hash(
            inputs,
            as_of=payload.asOf,
            periods=payload.periods,
            visibility_policy={"version": policy_version, **policy},
        )
        for customer_id, inputs in inputs_by_customer.items()
    }
    input_hash = _canonical_hash(hashes)
    ref = checkpoint_ref(
        "BATCH",
        customer_ids=payload.customerIds,
        checkpoint_key=payload.checkpointKey,
    )
    existing = find_checkpoint(session, ref)
    if existing is not None and existing.input_hash == input_hash:
        save_checkpoint(
            session,
            batch_ref=ref,
            input_hash=input_hash,
            row_count=existing.row_count,
            request=request,
            evaluated_at=evaluated_at,
            existing=existing,
        )
        return 0, len(payload.customerIds), 0, evaluated_at
    calculated = sum(
        persist_analytics_metrics(
            customer_id,
            payload.asOf,
            payload.periods,
            inputs_by_customer[customer_id],
            hashes[customer_id],
            session,
        )
        for customer_id in payload.customerIds
    )
    save_checkpoint(
        session,
        batch_ref=ref,
        input_hash=input_hash,
        row_count=calculated,
        request=request,
        evaluated_at=evaluated_at,
        existing=existing,
    )
    return len(payload.customerIds), 0, calculated, evaluated_at


@app.post(
    f"{PREFIX}/analytics/recompute",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecomputeResponse,
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Analytics"],
)
async def recompute(
    payload: RecomputeRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    validate_periods(payload.periods)
    if payload.mode == "HISTORICAL":
        calculated = 0
        evaluated_at = datetime.now(timezone.utc)
        for customer_id in payload.customerIds:
            calculated += await recompute_one(
                customer_id, payload.asOf, payload.periods, request, session
            )
        processed = len(payload.customerIds)
        skipped = 0
    elif payload.checkpointScope == "BATCH":
        processed, skipped, calculated, evaluated_at = await incremental_by_batch(
            payload, request, session
        )
    else:
        processed, skipped, calculated, evaluated_at = await incremental_by_customer(
            payload, request, session
        )
    # Le pipeline enchaîne immédiatement Signals puis Opportunity. `COMPLETED`
    # garantit donc que les snapshots sont visibles par le service suivant.
    session.commit()
    return {
        "jobId": str(deterministic_uuid("analytics-job", idempotency_key)),
        "status": "COMPLETED",
        "customers": len(payload.customerIds),
        "processed": processed,
        "skipped": skipped,
        "metrics": calculated,
        "asOf": payload.asOf.isoformat(),
        "mode": payload.mode,
        "checkpointScope": payload.checkpointScope,
        "lastEvaluatedAt": evaluated_at.isoformat(),
    }


@app.post(
    f"{PREFIX}/customers/{{customer_id}}/metrics/recalculate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecomputeResponse,
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
