from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    Customer,
    MetricSnapshot,
    RelationshipManager,
    Rule,
    RuleSimulation,
    RuleVersion,
)
from boa_oi.rules.domain import RuleEvaluator
from boa_oi.rules.service import audit


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
    for customer, manager, snapshot in customers.values():
        evaluation = evaluator.evaluate(
            version.configuration_json, metric_payload(snapshot.values_json)
        )
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
    audit(
        session,
        rule,
        version.version,
        "SIMULATED",
        actor,
        old={"status": rule.status},
        new={"simulationId": str(simulation.id), **result},
    )
    return simulation


__all__ = ["metric_payload", "simulate_persisted_history"]
