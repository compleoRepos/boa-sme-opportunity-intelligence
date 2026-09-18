from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.http_clients import service_request
from boa_oi.models.entities import Signal, SignalRule
from boa_oi.platform import (
    ANALYTICS_ROLES,
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
from boa_oi.signals.domain import MetricObservation
from boa_oi.signals.service import SignalDetector
from boa_oi.technical.config import SignalRuleConfig, active_rule_set
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app("signal-service", "Versioned signal detection with persisted evidence.")
PREFIX = "/internal/v1"
ENGINE_VERSION = "signal-0.1.0"


class DetectionRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    periods: list[str] = Field(default_factory=lambda: ["90D"])
    asOf: date
    ruleVersion: str | None = None


def analytics_url() -> str:
    value = os.getenv("ANALYTICS_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            "ANALYTICS_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def active_rules(session: Session) -> dict[str, SignalRuleConfig]:
    rows = list(session.scalars(select(SignalRule).where(SignalRule.active.is_(True))))
    if rows:
        return {
            row.rule_code: SignalRuleConfig.model_validate(row.configuration_json) for row in rows
        }
    return dict(active_rule_set().signal_rules)


def serialize(signal: Signal) -> dict[str, Any]:
    return {
        "signalId": signal.signal_ref,
        "customerId": signal.customer_ref,
        "type": signal.signal_type,
        "severity": signal.severity,
        "value": float(signal.value),
        "threshold": float(signal.threshold),
        "period": signal.evidence_json[0].get("period", "90D")
        if signal.evidence_json and isinstance(signal.evidence_json[0], dict)
        else "90D",
        "detectedAt": signal.detected_at.isoformat(),
        "status": signal.status,
        "evidence": signal.evidence_json,
        "metricReferences": [
            item.get("metric")
            for item in signal.evidence_json
            if isinstance(item, dict) and item.get("metric")
        ],
        "engineVersion": ENGINE_VERSION,
        "ruleVersion": signal.evidence_json[0].get("ruleVersion")
        if signal.evidence_json and isinstance(signal.evidence_json[0], dict)
        else None,
    }


def list_for(
    request: Request,
    session: Session,
    *,
    customer_id: str | None = None,
    page_size: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "customerId",
            "type",
            "severity",
            "fromDate",
            "toDate",
            "sort",
        },
    )
    offset = decode_cursor(cursor)
    params = request.query_params
    stmt = select(Signal)
    target_customer = customer_id or params.get("customerId")
    if target_customer:
        stmt = stmt.where(Signal.customer_id == deterministic_uuid("customer", target_customer))
    if params.get("type"):
        stmt = stmt.where(Signal.signal_type == params["type"])
    if params.get("severity"):
        stmt = stmt.where(Signal.severity == params["severity"])
    if params.get("fromDate"):
        stmt = stmt.where(
            Signal.detected_at
            >= datetime.combine(
                date.fromisoformat(params["fromDate"]), time.min, tzinfo=timezone.utc
            )
        )
    if params.get("toDate"):
        stmt = stmt.where(
            Signal.detected_at
            < datetime.combine(date.fromisoformat(params["toDate"]), time.min, tzinfo=timezone.utc)
        )
    sort = params.get("sort", "-detectedAt")
    column = {
        "detectedAt": Signal.detected_at,
        "severity": Signal.severity,
        "type": Signal.signal_type,
    }.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported signal sort field.")
    rows = list(
        session.scalars(
            stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), Signal.id)
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
    f"{PREFIX}/signals",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Signals"],
)
def list_signals(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(request, session, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/signals",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Signals"],
)
def customer_signals(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 100,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(request, session, customer_id=customer_id, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/signals/{{signal_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Signals"],
)
def get_signal(signal_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    item = session.scalar(select(Signal).where(Signal.signal_ref == signal_id))
    if item is None:
        raise not_found("Signal")
    return serialize(item)


@app.post(
    f"{PREFIX}/signals/evaluate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Signals"],
)
@app.post(
    f"{PREFIX}/detections",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Signals"],
)
async def evaluate(
    payload: DetectionRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rules = active_rules(session)
    created = 0
    corr = correlation_id(request)
    auth = request.headers.get("Authorization")
    for customer_id in payload.customerIds:
        for period in payload.periods:
            metrics_page = await service_request(
                "GET",
                f"{analytics_url()}/internal/v1/customers/{customer_id}/metrics",
                correlation_id=corr,
                params={"pageSize": 1000, "period": period},
                incoming_authorization=auth,
            )
            observations: dict[str, MetricObservation] = {}
            for row in metrics_page["data"]:
                observations[row["metric"]] = MetricObservation(
                    metric=row["metric"],
                    current_value=row["currentValue"],
                    previous_value=row.get("previousPeriodValue"),
                    growth_rate=row.get("growthRate"),
                    change=row.get("change"),
                    historical_baseline=row.get("historicalBaselineValue"),
                    sample_size=row.get("sampleSize") or 0,
                    data_coverage=row.get("dataCoverage") or 0,
                    quality_status=row.get("dataQuality") or "PARTIAL",
                    seasonality_adjusted=bool(row.get("seasonalityAdjusted", False)),
                    confirmation_count=2 if period in {"90D", "180D", "365D"} else 1,
                )
            detector = SignalDetector(rules, period=period)
            for found in detector.detect(customer_id, observations, payload.asOf):
                evidence = [
                    {
                        "text": text,
                        "metric": found.metric_reference,
                        "period": period,
                        "ruleVersion": found.rule_version,
                    }
                    for text in found.evidence
                ]
                session.execute(
                    pg_insert(Signal)
                    .values(
                        id=deterministic_uuid("signal-row", found.signal_id),
                        signal_ref=found.signal_id,
                        customer_id=deterministic_uuid("customer", customer_id),
                        customer_ref=customer_id,
                        signal_type=found.signal_type,
                        severity=found.severity,
                        value=Decimal(str(found.value)),
                        threshold=Decimal(str(found.threshold)),
                        detected_at=datetime.combine(payload.asOf, time.min, tzinfo=timezone.utc),
                        evidence_json=evidence,
                        status=found.status,
                        created_by="signal-service",
                    )
                    .on_conflict_do_update(
                        index_elements=[Signal.signal_ref],
                        set_={
                            "severity": found.severity,
                            "value": Decimal(str(found.value)),
                            "evidence_json": evidence,
                            "status": found.status,
                        },
                    )
                )
                created += 1
    return {
        "jobId": str(deterministic_uuid("signal-job", idempotency_key)),
        "status": "COMPLETED",
        "signals": created,
        "customers": len(payload.customerIds),
        "asOf": payload.asOf.isoformat(),
    }


__all__ = ["app"]
