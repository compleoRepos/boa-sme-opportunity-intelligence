from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.features import FEATURE_SET_VERSION
from boa_oi.features.domain import (
    AnalyticsSnapshot,
    CommercialIntelligenceSnapshot,
    CustomerProfile,
    FeatureBuilder,
)
from boa_oi.features.service import materialize_customer, serialize_feature
from boa_oi.http_clients import service_request
from boa_oi.models.entities import FeatureMaterialization
from boa_oi.platform import (
    ANALYTICS_ROLES,
    READ_ROLES,
    Problem,
    correlation_id,
    create_service_app,
    get_session,
    not_found,
    require_roles,
)
from boa_oi.rules import ENGINE_VERSION
from boa_oi.rules.simulation import metric_payload
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "feature-store-service",
    "Versioned features derived from Analytics, Signals, "
    "published Rule Studio evaluations and profiles.",
)
PREFIX = "/internal/v1/features"
DEPENDENCY_VARIABLES = {
    "customer": "CUSTOMER_SERVICE_URL",
    "analytics": "ANALYTICS_SERVICE_URL",
    "signal": "SIGNAL_SERVICE_URL",
    "rule_engine": "RULE_ENGINE_SERVICE_URL",
}


class MaterializeRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    asOf: date
    featureSetVersion: str = FEATURE_SET_VERSION


def _dependency_url(name: str) -> str | None:
    value = os.getenv(DEPENDENCY_VARIABLES[name])
    return value.rstrip("/") if value else None


def _runtime_dependencies_configured() -> bool:
    return all(_dependency_url(name) for name in DEPENDENCY_VARIABLES)


def _analytics_snapshots(
    rows: list[dict[str, Any]], as_of: date, customer_id: str
) -> list[AnalyticsSnapshot]:
    groups: dict[tuple[date, str], dict[str, Any]] = defaultdict(dict)
    for row in rows:
        row_as_of = date.fromisoformat(str(row["asOf"]))
        if row_as_of > as_of or row.get("period") != "90D":
            continue
        version = str(row.get("calculationVersion") or "unknown")
        groups[(row_as_of, version)][str(row["metric"])] = {
            "currentValue": row.get("currentValue"),
            "previousPeriodValue": row.get("previousPeriodValue"),
            "historicalBaselineValue": row.get("historicalBaselineValue"),
            "growthRate": row.get("growthRate"),
            "deviationFromBaseline": row.get("deviationFromBaseline"),
            "change": row.get("change"),
            "dataQuality": row.get("dataQuality"),
            "dataCoverage": row.get("dataCoverage"),
            "sampleSize": row.get("sampleSize"),
            "seasonalityAdjusted": row.get("seasonalityAdjusted"),
        }
    return [
        AnalyticsSnapshot(
            customer_id=customer_id,
            as_of=group_as_of,
            window_days=90,
            calculation_version=version,
            values=values,
            input_watermark=group_as_of.isoformat(),
        )
        for (group_as_of, version), values in sorted(groups.items())
    ]


def _rule_matches(payload: dict[str, Any]) -> list[dict[str, Any]]:
    matches = payload.get("matches")
    if isinstance(matches, list):
        return matches
    return [payload] if payload.get("matched") else []


async def _materialize_from_services(
    session: Session,
    customer_id: str,
    as_of: date,
    feature_set_version: str,
    request: Request,
) -> FeatureMaterialization:
    if feature_set_version != FEATURE_SET_VERSION:
        raise Problem(
            422,
            "UNSUPPORTED_FEATURE_SET",
            f"Unsupported feature set version: {feature_set_version}",
        )
    corr = correlation_id(request)
    authorization = request.headers.get("Authorization")
    customer = await service_request(
        "GET",
        f"{_dependency_url('customer')}/internal/v1/customers/{customer_id}",
        correlation_id=corr,
        incoming_authorization=authorization,
    )
    metrics_page = await service_request(
        "GET",
        f"{_dependency_url('analytics')}/internal/v1/customers/{customer_id}/metrics",
        correlation_id=corr,
        params={"period": "90D", "pageSize": 1_000},
        incoming_authorization=authorization,
    )
    signals_page = await service_request(
        "GET",
        f"{_dependency_url('signal')}/internal/v1/customers/{customer_id}/signals",
        correlation_id=corr,
        params={"pageSize": 1_000},
        incoming_authorization=authorization,
    )
    analytics = _analytics_snapshots(metrics_page["data"], as_of, customer_id)
    if not analytics:
        raise Problem(422, "ANALYTICS_SNAPSHOT_REQUIRED", "No 90D analytics snapshot is available.")
    latest = max(analytics, key=lambda item: (item.as_of, item.calculation_version))
    rule_response = await service_request(
        "POST",
        f"{_dependency_url('rule_engine')}/internal/v1/rules/evaluate",
        correlation_id=corr,
        json={"customerId": customer_id, "metrics": metric_payload(dict(latest.values))},
        incoming_authorization=authorization,
    )
    signals = [
        item
        for item in signals_page["data"]
        if date.fromisoformat(str(item["detectedAt"])[:10]) <= as_of
        and item.get("status") in {"OBSERVED", "CONFIRMED"}
    ]
    confirmed = sum(item.get("status") == "CONFIRMED" for item in signals)
    matches = _rule_matches(rule_response)
    intelligence = CommercialIntelligenceSnapshot(
        confirmed_signal_ratio=confirmed / len(signals) if signals else 0.0,
        published_rule_match_strength=max(
            (float(item.get("confidence") or 0) for item in matches), default=0.0
        ),
        signal_references=tuple(sorted(str(item["signalId"]) for item in signals)),
        active_rule_versions=tuple(
            sorted(str(item) for item in rule_response.get("evaluatedRuleVersions", []))
        ),
        matched_rule_versions=tuple(
            sorted(f"{item['ruleId']}:v{item['ruleVersion']}" for item in matches)
        ),
        rule_engine_version=str(rule_response.get("engineVersion") or ENGINE_VERSION),
    )
    try:
        vector = FeatureBuilder(feature_set_version).build(
            CustomerProfile(
                customer_id=customer_id,
                segment_code=str(customer["segment"]),
                incorporated_on=date.fromisoformat(str(customer["incorporatedOn"])),
            ),
            analytics,
            as_of,
            intelligence,
        )
    except ValueError as exc:
        raise Problem(422, "ANALYTICS_SNAPSHOT_REQUIRED", str(exc)) from exc

    customer_uuid = deterministic_uuid("customer", customer_id)
    existing = session.scalar(
        select(FeatureMaterialization).where(
            FeatureMaterialization.customer_id == customer_uuid,
            FeatureMaterialization.as_of_date == as_of,
            FeatureMaterialization.feature_set_version == feature_set_version,
        )
    )
    record = existing or FeatureMaterialization(
        id=deterministic_uuid("feature-materialization", customer_uuid, as_of, feature_set_version),
        customer_id=customer_uuid,
        customer_ref=customer_id,
        as_of_date=as_of,
        feature_set_version=feature_set_version,
        values_json=vector.values,
        sources_json=list(vector.sources),
        lineage_json=list(vector.lineage),
        checksum=vector.checksum,
        created_by="feature-store-service",
    )
    record.values_json = vector.values
    record.sources_json = list(vector.sources)
    record.lineage_json = list(vector.lineage)
    record.checksum = vector.checksum
    session.add(record)
    session.flush()
    return record


async def _materialize_customer(
    session: Session,
    customer_id: str,
    as_of: date,
    feature_set_version: str,
    request: Request,
) -> FeatureMaterialization:
    if _runtime_dependencies_configured():
        return await _materialize_from_services(
            session, customer_id, as_of, feature_set_version, request
        )
    # Unit-test fallback only. Runtime Compose configures every service URL.
    return materialize_customer(session, customer_id, as_of, feature_set_version)


@app.post(
    f"{PREFIX}/materialize",
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Feature Store"],
)
async def materialize(
    payload: MaterializeRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    records = [
        await _materialize_customer(
            session,
            customer_id,
            payload.asOf,
            payload.featureSetVersion,
            request,
        )
        for customer_id in payload.customerIds
    ]
    return {
        "data": [serialize_feature(item) for item in records],
        "meta": {
            "customers": len(records),
            "asOf": payload.asOf.isoformat(),
            "featureSetVersion": payload.featureSetVersion,
        },
    }


@app.post(
    f"{PREFIX}/customers/{{customer_id}}/materialize",
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Feature Store"],
)
async def materialize_one(
    customer_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    feature_set_version: Annotated[str, Query(alias="featureSetVersion")] = FEATURE_SET_VERSION,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return serialize_feature(
        await _materialize_customer(session, customer_id, as_of, feature_set_version, request)
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Feature Store"],
)
def get_materialized(
    customer_id: str,
    as_of: Annotated[date, Query(alias="asOf")],
    feature_set_version: Annotated[str, Query(alias="featureSetVersion")] = FEATURE_SET_VERSION,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = session.scalar(
        select(FeatureMaterialization).where(
            FeatureMaterialization.customer_ref == customer_id,
            FeatureMaterialization.as_of_date == as_of,
            FeatureMaterialization.feature_set_version == feature_set_version,
        )
    )
    if record is None:
        raise not_found("Feature materialization")
    return serialize_feature(record)


__all__ = ["app"]
