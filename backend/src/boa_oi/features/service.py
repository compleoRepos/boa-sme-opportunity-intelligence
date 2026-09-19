from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import Customer, FeatureMaterialization, MetricSnapshot, Signal
from boa_oi.platform import Problem, not_found
from boa_oi.rules import ENGINE_VERSION, RuleEvaluator
from boa_oi.rules.service import active_versions
from boa_oi.technical.ids import deterministic_uuid

from .domain import (
    FEATURE_SET_VERSION,
    AnalyticsSnapshot,
    CommercialIntelligenceSnapshot,
    CustomerProfile,
    FeatureBuilder,
    FeatureVector,
)


def find_customer(session: Session, customer_identifier: str) -> Customer:
    customer = session.scalar(select(Customer).where(Customer.customer_ref == customer_identifier))
    if customer is None:
        try:
            customer_uuid = UUID(customer_identifier)
        except ValueError:
            customer_uuid = None
        if customer_uuid is not None:
            customer = session.get(Customer, customer_uuid)
    if customer is None:
        raise not_found("Customer")
    return customer


def _analytics_inputs(session: Session, customer: Customer, as_of: date) -> list[AnalyticsSnapshot]:
    records = list(
        session.scalars(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.customer_id == customer.id,
                MetricSnapshot.as_of_date <= as_of,
                MetricSnapshot.window_days == 90,
            )
            .order_by(MetricSnapshot.as_of_date, MetricSnapshot.calculation_version)
        )
    )
    return [
        AnalyticsSnapshot(
            customer_id=customer.customer_ref,
            as_of=item.as_of_date,
            window_days=item.window_days,
            calculation_version=item.calculation_version,
            values=item.values_json,
            input_watermark=item.input_watermark,
        )
        for item in records
    ]


def _rule_metrics(snapshot: AnalyticsSnapshot) -> dict[str, Any]:
    aliases = {
        "inflow_amount": "INFLOW_GROWTH",
        "supplier_payment_amount": "SUPPLIER_PAYMENT_GROWTH",
        "transaction_count": "TRANSACTION_VOLUME_GROWTH",
        "international_flow_amount": "INTERNATIONAL_FLOW_GROWTH",
        "average_balance": "BALANCE_SURPLUS",
        "credit_line_utilization": "CREDIT_UTILIZATION_INCREASE",
    }
    metrics: dict[str, Any] = {}
    for code, raw in snapshot.values.items():
        value: Any = raw
        alias = aliases.get(code)
        if alias and alias.endswith("_GROWTH"):
            value = raw.get("growthRate")
        elif alias == "CREDIT_UTILIZATION_INCREASE":
            value = raw.get("change")
        metrics[code] = raw
        if alias:
            metrics[alias] = value
    return metrics


def _commercial_intelligence(
    session: Session,
    customer: Customer,
    as_of: date,
    analytics: list[AnalyticsSnapshot],
) -> CommercialIntelligenceSnapshot:
    signals = list(
        session.scalars(
            select(Signal).where(
                Signal.customer_id == customer.id,
                func.date(Signal.detected_at) <= as_of,
                Signal.status.in_(("OBSERVED", "CONFIRMED")),
            )
        )
    )
    confirmed = sum(item.status == "CONFIRMED" for item in signals)
    confirmed_ratio = confirmed / len(signals) if signals else 0.0
    latest = max(analytics, key=lambda item: (item.as_of, item.calculation_version))
    evaluator = RuleEvaluator()
    active = active_versions(session)
    matches: list[tuple[str, float]] = []
    versions: list[str] = []
    for rule, version in active:
        identifier = f"{rule.rule_id}:v{version.version}"
        versions.append(identifier)
        evaluation = evaluator.evaluate(version.configuration_json, _rule_metrics(latest))
        if evaluation.matched:
            matches.append((identifier, float(evaluation.confidence)))
    return CommercialIntelligenceSnapshot(
        confirmed_signal_ratio=confirmed_ratio,
        published_rule_match_strength=max((score for _identifier, score in matches), default=0.0),
        signal_references=tuple(sorted(item.signal_ref for item in signals)),
        active_rule_versions=tuple(sorted(versions)),
        matched_rule_versions=tuple(sorted(identifier for identifier, _score in matches)),
        rule_engine_version=ENGINE_VERSION,
    )


def materialize_customer(
    session: Session,
    customer_identifier: str,
    as_of: date,
    feature_set_version: str = FEATURE_SET_VERSION,
) -> FeatureMaterialization:
    if feature_set_version != FEATURE_SET_VERSION:
        raise Problem(
            422,
            "UNSUPPORTED_FEATURE_SET",
            f"Unsupported feature set version: {feature_set_version}",
        )
    customer = find_customer(session, customer_identifier)
    builder = FeatureBuilder(feature_set_version)
    try:
        analytics = _analytics_inputs(session, customer, as_of)
        vector = builder.build(
            CustomerProfile(
                customer_id=customer.customer_ref,
                segment_code=customer.segment_code,
                incorporated_on=customer.incorporated_on,
            ),
            analytics,
            as_of,
            _commercial_intelligence(session, customer, as_of, analytics),
        )
    except ValueError as exc:
        raise Problem(422, "ANALYTICS_SNAPSHOT_REQUIRED", str(exc)) from exc

    existing = session.scalar(
        select(FeatureMaterialization).where(
            FeatureMaterialization.customer_id == customer.id,
            FeatureMaterialization.as_of_date == as_of,
            FeatureMaterialization.feature_set_version == feature_set_version,
        )
    )
    record = existing or FeatureMaterialization(
        id=deterministic_uuid("feature-materialization", customer.id, as_of, feature_set_version),
        customer_id=customer.id,
        customer_ref=customer.customer_ref,
        as_of_date=as_of,
        feature_set_version=feature_set_version,
        values_json=vector.values,
        sources_json=list(vector.sources),
        lineage_json=list(vector.lineage),
        checksum=vector.checksum,
        created_by="feature-store-service",
    )
    record.customer_ref = customer.customer_ref
    record.values_json = vector.values
    record.sources_json = list(vector.sources)
    record.lineage_json = list(vector.lineage)
    record.checksum = vector.checksum
    session.add(record)
    session.flush()
    return record


def vector_from_record(record: FeatureMaterialization) -> FeatureVector:
    return FeatureVector(
        customer_id=record.customer_ref,
        as_of=record.as_of_date,
        feature_set_version=record.feature_set_version,
        values={name: float(value) for name, value in record.values_json.items()},
        sources=tuple(record.sources_json),
        lineage=tuple(record.lineage_json),
        checksum=record.checksum,
    )


def serialize_feature(record: FeatureMaterialization) -> dict[str, Any]:
    return {
        "customerId": record.customer_ref,
        "asOf": record.as_of_date.isoformat(),
        "featureSetVersion": record.feature_set_version,
        "values": record.values_json,
        "sources": record.sources_json,
        "lineage": record.lineage_json,
        "checksum": record.checksum,
    }


__all__ = [
    "find_customer",
    "materialize_customer",
    "serialize_feature",
    "vector_from_record",
]
