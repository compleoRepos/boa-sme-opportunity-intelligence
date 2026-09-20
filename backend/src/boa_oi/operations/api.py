from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from math import isfinite
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.models.entities import MLGovernanceAuditLog, MLMonitoringSnapshot
from boa_oi.operations.monitoring import (
    DriftDomain,
    DriftMonitor,
    DriftThresholds,
    OperationalMetrics,
    OperationalMonitor,
    OperationalThresholds,
)
from boa_oi.platform import READ_ROLES, correlation_id, get_session, require_roles

PREFIX = "/internal/v1"
MONITORING_DOMAINS = ("DATA", "FEATURE", "PREDICTION", "OPERATIONAL")
READINESS_COMPONENTS = (
    "RULE_ENGINE",
    "FEATURE_STORE",
    "ML_ENGINE",
    "OPPORTUNITY_ENGINE",
    "SCORING_POLICY",
    "MODEL_REGISTRY",
    "MONITORING",
    "FALLBACK",
    "SECURITY",
    "AUDIT",
    "DATA_GOVERNANCE",
    "OBSERVABILITY",
)

# These are deliberately not inferred from health checks.  They are the production
# claims which must be explicitly attested by an integration owner before READY.
PRODUCTION_PROOFS = (
    "realDataGoverned",
    "labelsSufficient",
    "mlValidation",
    "approvedModel",
    "monitoring",
    "fallback",
    "security",
    "prodSecrets",
    "ha",
    "backup",
    "realIntegrations",
)

router = APIRouter(prefix=PREFIX)
# A descriptive alias makes integration code explicit without creating a second router.
operations_router = router


class MonitoringDomain(str, Enum):
    DATA = "DATA"
    FEATURE = "FEATURE"
    PREDICTION = "PREDICTION"
    OPERATIONAL = "OPERATIONAL"


class MonitoringObservationIn(BaseModel):
    """One immutable monitoring sample.

    Drift observations use ``value`` and ``thresholds``.  Operational observations
    may additionally provide the explicit counters below (or a ``metrics`` object).
    Unknown fields are retained by Pydantic so adapters can carry domain-specific
    evidence without losing it in the audit record.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    domain: MonitoringDomain
    metric: str = Field(min_length=1, max_length=80)
    value: float | None = None
    thresholds: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime | None = Field(default=None, alias="observedAt")
    trace_id: str | None = Field(default=None, alias="traceId")
    segment: str = "ALL"
    sample_size: int | None = Field(default=None, alias="sampleSize", ge=0)
    reference_version: str | None = Field(default=None, alias="referenceVersion")
    population: str | None = None

    latency_ms: float | None = Field(default=None, alias="latencyMs")
    errors: int = Field(default=0, ge=0)
    requests: int = Field(default=0, ge=0)
    volume: int = Field(default=0, ge=0)
    rules_only_count: int = Field(default=0, alias="rulesOnlyCount", ge=0)
    metrics: dict[str, Any] | None = None

    @field_validator("value", "latency_ms")
    @classmethod
    def finite_number(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(float(value)):
            raise ValueError("metric values must be finite numbers")
        return value

    @field_validator("observed_at")
    @classmethod
    def timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("observedAt must include a timezone")
        return value


class MonitoringObservationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    domain: str
    metric: str
    value: float
    status: str
    thresholds: dict[str, Any]
    details: dict[str, Any]
    observed_at: datetime = Field(alias="observedAt")
    trace_id: str = Field(alias="traceId")


class ReadinessComponentOut(BaseModel):
    name: str
    status: Literal["READY", "WARNING", "BLOCKED"]
    evidence: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ReadinessOut(BaseModel):
    status: Literal["READY", "WARNING", "BLOCKED"]
    overall_status: Literal["READY", "WARNING", "BLOCKED"] = Field(alias="overallStatus")
    components: list[ReadinessComponentOut]
    checks: list[ReadinessComponentOut]
    blocking_components: list[str] = Field(alias="blockingComponents")
    component_statuses: dict[str, str] = Field(alias="componentStatuses")
    deployment_mode: Literal["POC_SHADOW"] = Field(alias="deploymentMode")
    production_performance_claim: Literal[False] = Field(alias="productionPerformanceClaim")
    generated_at: datetime = Field(alias="generatedAt")


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current if current.tzinfo is not None else current.replace(tzinfo=timezone.utc)


def _finite(value: Any, *, field_name: str = "value") -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{field_name} must be a finite number")
    return result


def _metric_value(value: float) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("value must be a valid decimal") from exc
    if not result.is_finite():
        raise ValueError("value must be finite")
    return result


def _threshold_payload(thresholds: dict[str, Any]) -> dict[str, Any]:
    # Copy through JSON to ensure the ORM JSON column never receives a Pydantic
    # object, Enum, Decimal, or another non-serializable value.
    return json.loads(json.dumps(thresholds, default=str))


def _operational_input(payload: MonitoringObservationIn) -> dict[str, Any]:
    source = dict(payload.metrics or {})
    # Top-level fields are the convenient HTTP contract; an explicit metrics object
    # wins only where it actually supplied a value.
    values: dict[str, Any] = {
        "latency_ms": payload.latency_ms,
        "errors": payload.errors,
        "requests": payload.requests,
        "volume": payload.volume,
        "rules_only_count": payload.rules_only_count,
    }
    aliases = {
        "latencyMs": "latency_ms",
        "rulesOnlyCount": "rules_only_count",
    }
    for key, value in list(source.items()):
        source[aliases.get(key, key)] = value
    for key, value in source.items():
        if value is not None:
            values[key] = value
    if values["latency_ms"] is None:
        values["latency_ms"] = (
            payload.value
            if payload.metric.lower()
            in {
                "latency",
                "latency_ms",
                "latencyms",
            }
            else 0.0
        )
    values["observed_at"] = _as_utc(payload.observed_at)
    return values


def _observe(payload: MonitoringObservationIn) -> tuple[float, str, dict[str, Any], dict[str, Any]]:
    """Run the pure operations-domain monitor and return persistence-ready data."""

    thresholds = _threshold_payload(payload.thresholds)
    if payload.domain is MonitoringDomain.OPERATIONAL:
        operational_observation = OperationalMonitor(
            OperationalThresholds.from_mapping(thresholds)
        ).observe(OperationalMetrics(**_operational_input(payload)))
        result = operational_observation.to_dict()
        value = payload.value
        if value is None:
            metric_key = payload.metric
            by_metric = {
                "latency": operational_observation.metrics.latency_ms,
                "latency_ms": operational_observation.metrics.latency_ms,
                "error_rate": operational_observation.metrics.error_rate,
                "errorRate": operational_observation.metrics.error_rate,
                "volume": operational_observation.metrics.volume,
                "rules_only_rate": operational_observation.metrics.rules_only_rate,
                "rulesOnlyRate": operational_observation.metrics.rules_only_rate,
            }
            value = float(by_metric.get(metric_key, operational_observation.metrics.latency_ms))
        status = operational_observation.severity.value
        return _finite(value), status, thresholds, {**payload.details, **result}

    if payload.value is None:
        raise ValueError("value is required for DATA, FEATURE, and PREDICTION observations")
    drift_thresholds = DriftThresholds.from_mapping(thresholds)
    drift_observation = DriftMonitor().observe(
        DriftDomain(payload.domain.value),
        payload.metric,
        _finite(payload.value),
        segment=payload.segment,
        sample_size=payload.sample_size,
        reference_version=payload.reference_version,
        population=payload.population,
        thresholds=drift_thresholds,
    )
    return (
        float(drift_observation.value),
        drift_observation.severity.value,
        {**thresholds, **drift_thresholds.to_dict()},
        {**payload.details, **drift_observation.to_dict()},
    )


def _serialize_snapshot(snapshot: MLMonitoringSnapshot) -> dict[str, Any]:
    return {
        "id": str(snapshot.id),
        "domain": snapshot.domain,
        "metric": snapshot.metric,
        "value": float(snapshot.value),
        "status": snapshot.status,
        "thresholds": snapshot.thresholds_json or {},
        "details": snapshot.details_json or {},
        "observedAt": _as_utc(snapshot.observed_at).isoformat(),
        "traceId": snapshot.trace_id,
    }


def _audit(
    *,
    principal: Any,
    snapshot: MLMonitoringSnapshot,
    payload: dict[str, Any],
    trace_id: str,
) -> MLGovernanceAuditLog:
    return MLGovernanceAuditLog(
        id=uuid4(),
        action="MONITORING_OBSERVATION_RECORDED",
        user_id=str(getattr(principal, "subject", "system")),
        timestamp=datetime.now(timezone.utc),
        object_type="MLMonitoringSnapshot",
        object_id=str(snapshot.id),
        object_version="1",
        old_value_json=None,
        new_value_json=payload,
        reason="Immutable monitoring observation persisted",
        trace_id=trace_id,
    )


@router.post(
    "/monitoring/observations",
    response_model=MonitoringObservationOut,
    status_code=201,
    tags=["Operations"],
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def record_monitoring_observation(
    payload: MonitoringObservationIn,
    request: Request,
    session: Session = Depends(get_session),
    principal: Any = Depends(require_roles(*READ_ROLES)),
) -> dict[str, Any]:
    try:
        value, severity, threshold_json, details = _observe(payload)
    except (TypeError, ValueError) as exc:
        # Let FastAPI's normal validation shape remain stable while keeping domain
        # validation errors useful to API clients.
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc

    trace_id = payload.trace_id or correlation_id(request)
    observed_at = _as_utc(payload.observed_at)
    snapshot = MLMonitoringSnapshot(
        id=uuid4(),
        domain=payload.domain.value,
        metric=payload.metric,
        value=_metric_value(value),
        status=severity,
        thresholds_json=threshold_json,
        details_json=details,
        observed_at=observed_at,
        trace_id=trace_id,
    )
    session.add(snapshot)
    session.add(
        _audit(
            principal=principal,
            snapshot=snapshot,
            payload={
                "domain": snapshot.domain,
                "metric": snapshot.metric,
                "value": value,
                "status": severity,
                "traceId": trace_id,
            },
            trace_id=trace_id,
        )
    )
    return _serialize_snapshot(snapshot)


@router.get(
    "/monitoring/history",
    tags=["Operations"],
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def monitoring_history(
    request: Request,
    domain: MonitoringDomain | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(MLMonitoringSnapshot).order_by(
        MLMonitoringSnapshot.observed_at.desc(), MLMonitoringSnapshot.id.desc()
    )
    if domain is not None:
        statement = statement.where(MLMonitoringSnapshot.domain == domain.value)
    rows = list(session.scalars(statement.limit(limit)))
    data = [_serialize_snapshot(row) for row in rows]
    return {
        "data": data,
        "snapshots": data,
        "meta": {"limit": limit, "count": len(data), "domain": domain.value if domain else None},
        "correlationId": correlation_id(request),
    }


def _readiness_source(request: Request) -> dict[str, Any]:
    configured = getattr(request.app.state, "readiness_evidence", None)
    if isinstance(configured, dict):
        return configured
    raw = os.getenv("BOA_READINESS_EVIDENCE", "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _explicit_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, dict):
        return (
            value.get("proven") is True
            or value.get("passed") is True
            or value.get("status") == "READY"
        )
    return False


def _readiness(request: Request) -> dict[str, Any]:
    evidence = _readiness_source(request)
    gates = evidence.get("productionGates", {})
    if not isinstance(gates, dict):
        gates = {}
    components: list[dict[str, Any]] = []
    for name in READINESS_COMPONENTS:
        raw = evidence.get(name)
        item = raw if isinstance(raw, dict) else {"proven": raw is True}
        status = str(item.get("status", "READY" if _explicit_true(raw) else "BLOCKED")).upper()
        if status not in {"READY", "WARNING", "BLOCKED"}:
            status = "BLOCKED"
        # Explicit hard proofs are mandatory even if a component was marked READY.
        required_gates: tuple[str, ...] = {
            "ML_ENGINE": ("labelsSufficient", "mlValidation"),
            "MODEL_REGISTRY": ("approvedModel",),
            "MONITORING": ("monitoring",),
            "FALLBACK": ("fallback",),
            "SECURITY": ("security", "prodSecrets"),
            "DATA_GOVERNANCE": ("realDataGoverned",),
            "OBSERVABILITY": ("ha", "backup", "realIntegrations"),
        }.get(name, ())
        missing = [
            gate
            for gate in required_gates
            if not _explicit_true(gates.get(gate)) and not _explicit_true(item.get(gate))
        ]
        if missing:
            status = "BLOCKED"
            item = {**item, "missingProofs": missing}
        components.append(
            {
                "name": name,
                "status": status,
                "evidence": item.get("evidence"),
                "details": {
                    key: value for key, value in item.items() if key not in {"status", "evidence"}
                },
            }
        )
    statuses = {item["name"]: item["status"] for item in components}
    blocking = [name for name, status in statuses.items() if status == "BLOCKED"]
    warnings = [name for name, status in statuses.items() if status == "WARNING"]
    overall = "BLOCKED" if blocking else "WARNING" if warnings else "READY"
    # A second global guard prevents a future component addition from silently
    # weakening the production gate.
    if overall == "READY" and any(not _explicit_true(gates.get(key)) for key in PRODUCTION_PROOFS):
        overall = "BLOCKED"
        for item in components:
            if (
                item["name"]
                in {"ML_ENGINE", "MODEL_REGISTRY", "SECURITY", "DATA_GOVERNANCE", "OBSERVABILITY"}
                and item["status"] == "READY"
            ):
                item["status"] = "BLOCKED"
                missing_proofs = [
                    key for key in PRODUCTION_PROOFS if not _explicit_true(gates.get(key))
                ]
                item["details"] = {
                    **item["details"],
                    "missingProofs": missing_proofs,
                }
        statuses = {item["name"]: item["status"] for item in components}
        blocking = [name for name, status in statuses.items() if status == "BLOCKED"]
    return {
        "status": overall,
        "overallStatus": overall,
        "components": components,
        "checks": components,
        "blockingComponents": blocking,
        "componentStatuses": statuses,
        "deploymentMode": "POC_SHADOW",
        "productionPerformanceClaim": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/readiness",
    response_model=ReadinessOut,
    tags=["Operations"],
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def readiness(request: Request) -> dict[str, Any]:
    return _readiness(request)


__all__ = [
    "PREFIX",
    "READINESS_COMPONENTS",
    "MonitoringDomain",
    "MonitoringObservationIn",
    "MonitoringObservationOut",
    "ReadinessOut",
    "operations_router",
    "readiness",
    "record_monitoring_observation",
    "router",
]
