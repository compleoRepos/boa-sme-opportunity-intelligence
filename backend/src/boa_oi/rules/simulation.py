from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    Customer,
    FlowVisibilityPolicy,
    FlowVisibilitySnapshot,
    MetricSnapshot,
    OpportunityAction,
    RelationshipManager,
    Rule,
    RuleSimulation,
    RuleVersion,
)
from boa_oi.rules.domain import RuleEvaluator


def _confidence_level(score: float) -> str:
    if score >= 0.8:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"


METRIC_ALIASES = {
    "inflow_amount": "INFLOW_GROWTH",
    "supplier_payment_amount": "SUPPLIER_PAYMENT_GROWTH",
    "transaction_count": "TRANSACTION_VOLUME_GROWTH",
    "international_flow_amount": "INTERNATIONAL_FLOW_GROWTH",
    "average_balance": "BALANCE_SURPLUS",
    "credit_line_utilization": "CREDIT_UTILIZATION_INCREASE",
}


def metric_payload(values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for code, item in values.items():
        if isinstance(item, dict):
            result[code] = {
                "currentValue": item.get("currentValue"),
                "previousPeriodValue": item.get("previousPeriodValue"),
                "growthRate": item.get("growthRate"),
                "change": item.get("change"),
                "history": item.get("history", []),
            }
        else:
            result[code] = item
        alias = METRIC_ALIASES.get(code)
        if alias:
            if isinstance(item, dict) and alias.endswith("_GROWTH"):
                result[alias] = item.get("growthRate")
            elif isinstance(item, dict) and alias == "CREDIT_UTILIZATION_INCREASE":
                result[alias] = item.get("change")
            else:
                result[alias] = result[code]
    return result


def visibility_metric_payload(
    visibility: FlowVisibilitySnapshot | None,
    *,
    has_recent_domiciliation_action: bool,
) -> dict[str, Any]:
    level = visibility.level if visibility is not None else "UNKNOWN"
    fingerprint_growth = (
        visibility.fingerprint_count_90d - visibility.fingerprint_previous_90d
        if visibility is not None
        else 0
    )
    return {
        "FLOW_VISIBILITY_OPPORTUNITY": level in {"PARTIAL", "LOW"},
        "FLOW_VISIBILITY_LEVEL": level,
        "FLOW_VISIBILITY_SHARE": (
            float(visibility.estimated_share)
            if visibility is not None and visibility.estimated_share is not None
            else None
        ),
        "FINGERPRINT_GROWTH_90D": fingerprint_growth,
        "DECLARED_TURNOVER_GROWTH": 0.0,
        "NO_RECENT_DOMICILIATION_ACTION": not has_recent_domiciliation_action,
    }


def has_action_table(session: Session) -> bool:
    connection = session.connection()
    return inspect(connection).has_table(
        OpportunityAction.__tablename__, schema=OpportunityAction.__table__.schema
    )


def active_domiciliation_cooldown_days(session: Session) -> int:
    connection = session.connection()
    if not inspect(connection).has_table(
        FlowVisibilityPolicy.__tablename__, schema=FlowVisibilityPolicy.__table__.schema
    ):
        return 180
    policy = session.scalar(
        select(FlowVisibilityPolicy)
        .where(FlowVisibilityPolicy.active.is_(True))
        .order_by(FlowVisibilityPolicy.version.desc())
        .limit(1)
    )
    if policy is None:
        return 180
    return int(policy.configuration_json.get("domiciliationCooldownDays", 180))


def simulate_persisted_history(
    session: Session,
    rule: Rule,
    version: RuleVersion,
    *,
    period_from: date,
    period_to: date,
    population: dict[str, Any],
    actor: str,
    broad_rule_threshold: float = 0.5,
) -> RuleSimulation:
    segment = population.get("segment")
    sector = population.get("sector")
    stmt = (
        select(Customer, RelationshipManager, MetricSnapshot)
        .join(RelationshipManager, Customer.rm_id == RelationshipManager.id)
        .join(MetricSnapshot, MetricSnapshot.customer_id == Customer.id)
        .where(
            Customer.status == "ACTIVE",
            MetricSnapshot.as_of_date >= period_from,
            MetricSnapshot.as_of_date <= period_to,
        )
        .order_by(Customer.id, MetricSnapshot.as_of_date.desc(), MetricSnapshot.window_days.desc())
    )
    if segment and str(segment).upper() != "SME":
        stmt = stmt.where(Customer.segment_code == str(segment))
    if sector and sector != "ALL":
        stmt = stmt.where(Customer.sector_code == str(sector))
    rows = session.execute(stmt).all()
    # The latest relevant snapshot per customer is an Analytics feature, never raw transaction work.
    customers: dict[UUID, tuple[Customer, RelationshipManager, MetricSnapshot]] = {}
    requested_periods = {
        int(str(node.get("period", "0D")).removesuffix("D"))
        for node in version.configuration_json.get("conditions", [])
        if isinstance(node, dict) and str(node.get("period", "")).endswith("D")
    }
    for customer, manager, snapshot in rows:
        existing = customers.get(customer.id)
        preferred = not requested_periods or snapshot.window_days in requested_periods
        if existing is None or (preferred and existing[2].window_days not in requested_periods):
            customers[customer.id] = (customer, manager, snapshot)
    evaluator = RuleEvaluator()
    matches: list[dict[str, Any]] = []
    sector_distribution: Counter[str] = Counter()
    segment_distribution: Counter[str] = Counter()
    region_distribution: Counter[str] = Counter()
    rm_distribution: Counter[str] = Counter()
    confidence_distribution: Counter[str] = Counter()
    recommendation = version.configuration_json["recommendation"]
    domiciliation_cooldown_days = active_domiciliation_cooldown_days(session)
    for customer, manager, snapshot in customers.values():
        visibility = session.scalar(
            select(FlowVisibilitySnapshot)
            .where(
                FlowVisibilitySnapshot.customer_id == customer.id,
                FlowVisibilitySnapshot.as_of_date <= period_to,
            )
            .order_by(FlowVisibilitySnapshot.as_of_date.desc())
            .limit(1)
        )
        recent_action_cutoff = datetime.combine(
            period_to - timedelta(days=domiciliation_cooldown_days - 1),
            time.min,
            tzinfo=timezone.utc,
        )
        has_recent_domiciliation_action = has_action_table(session) and (
            session.scalar(
                select(OpportunityAction.id)
                .where(
                    OpportunityAction.customer_id == customer.id,
                    OpportunityAction.created_at >= recent_action_cutoff,
                    OpportunityAction.created_at
                    < datetime.combine(
                        period_to + timedelta(days=1), time.min, tzinfo=timezone.utc
                    ),
                    OpportunityAction.opportunity_type == "FLOW_DOMICILIATION",
                )
                .limit(1)
            )
            is not None
        )
        metrics = metric_payload(snapshot.values_json)
        metrics.update(
            visibility_metric_payload(
                visibility,
                has_recent_domiciliation_action=has_recent_domiciliation_action,
            )
        )
        for code, value in tuple(metrics.items()):
            if ":" not in code:
                metrics[f"{code}:{snapshot.window_days}D"] = value
        evaluation = evaluator.evaluate(version.configuration_json, metrics)
        if not evaluation.matched:
            continue
        confidence_level = _confidence_level(evaluation.confidence)
        confidence_distribution[confidence_level] += 1
        sector_distribution[customer.sector_code] += 1
        segment_distribution[customer.segment_code] += 1
        region_distribution[manager.branch_code] += 1
        rm_distribution[manager.subject_id] += 1
        matches.append(
            {
                "customerId": customer.customer_ref,
                "company": customer.legal_name,
                "legalName": customer.legal_name,
                "signals": [item["metric"] for item in evaluation.evidence if item["result"]],
                "values": {item["metric"]: item["actual"] for item in evaluation.evidence},
                "confidence": evaluation.confidence,
                "confidenceLevel": confidence_level,
                "opportunity": recommendation["opportunityType"],
                "opportunityType": recommendation["opportunityType"],
                "products": recommendation.get("products", []),
                "ruleId": rule.rule_id,
                "ruleVersion": version.version,
            }
        )
    matches.sort(key=lambda item: (-float(item["confidence"]), str(item["customerId"])))
    population_analyzed = len(customers)
    matched_customers = len(matches)
    match_rate = matched_customers / population_analyzed if population_analyzed else 0.0
    warning = None
    if match_rate >= broad_rule_threshold:
        warning = {
            "code": "RULE_TOO_BROAD",
            "message": (
                f"This rule would generate opportunities for {match_rate:.1%} "
                "of the analyzed population. This may indicate an overly permissive rule."
            ),
            "blocking": False,
            "affectedRate": match_rate,
        }
    by_sector = [
        {
            "sector": key,
            "count": value,
            "rate": value / matched_customers if matched_customers else 0,
        }
        for key, value in sorted(sector_distribution.items())
    ]
    by_region = [
        {
            "region": key,
            "count": value,
            "rate": value / matched_customers if matched_customers else 0,
        }
        for key, value in sorted(region_distribution.items())
    ]
    by_segment = [
        {
            "segment": key,
            "count": value,
            "rate": value / matched_customers if matched_customers else 0,
        }
        for key, value in sorted(segment_distribution.items())
    ]
    result: dict[str, Any] = {
        "populationAnalyzed": population_analyzed,
        "matchedCustomers": matched_customers,
        "highConfidence": confidence_distribution["HIGH"],
        "mediumConfidence": confidence_distribution["MEDIUM"],
        "lowConfidence": confidence_distribution["LOW"],
        "conversionRate": "NOT_AVAILABLE",
        "matchRate": match_rate,
        "potentialOpportunities": matched_customers,
        "preview": matches[:20],
        "topCustomers": matches[:20],
        "warnings": [warning] if warning else [],
        "averageOpportunitiesPerRm": (
            matched_customers / len(rm_distribution) if rm_distribution else 0.0
        ),
        "impact": {
            "populationAffected": matched_customers,
            "opportunitiesGenerated": matched_customers,
            "averageOpportunitiesPerRM": (
                matched_customers / len(rm_distribution) if rm_distribution else 0.0
            ),
            "distributionBySector": dict(sector_distribution),
            "distributionByRegion": dict(region_distribution),
            "distributionByCustomerSegment": dict(segment_distribution),
            "bySector": by_sector,
            "byRegion": by_region,
            "bySegment": by_segment,
        },
        "warning": warning,
    }
    simulation = RuleSimulation(
        id=uuid4(),
        rule_version_id=version.id,
        period_from=period_from,
        period_to=period_to,
        population_json=population,
        result_json=result,
        created_at=datetime.now(timezone.utc),
        created_by=actor,
    )
    session.add(simulation)
    return simulation


__all__ = [
    "has_action_table",
    "metric_payload",
    "simulate_persisted_history",
    "visibility_metric_payload",
]
