from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.audit import DecisionAuditBuilder
from boa_oi.catalog import family_status
from boa_oi.http_clients import service_request
from boa_oi.models.entities import (
    DecisionAudit,
    Opportunity,
    OpportunityEvidence,
    OpportunityRule,
)
from boa_oi.opportunities import OpportunityCandidate, OpportunityContext, OpportunityEngine
from boa_oi.opportunities.domain import ConditionEvidence
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
from boa_oi.technical.config import (
    OpportunityRuleConfig,
    RuleSetConfig,
    active_rule_set,
)
from boa_oi.technical.ids import deterministic_uuid

HORIZON_LABELS = {
    "0-1_MONTH": "Contacter dans le mois.",
    "0-3_MONTHS": "Contacter dans les 3 mois.",
    "1-3_MONTHS": "Contacter dans les 1 à 3 mois.",
    "3-6_MONTHS": "Contacter dans les 3 à 6 mois.",
}

app = create_service_app(
    "opportunity-service",
    "Deterministic, versioned, explainable and audited SME opportunities.",
)
PREFIX = "/internal/v1"
ML_PRIORITY_WEIGHT = float(os.getenv("ML_PRIORITY_WEIGHT", "0.35"))
RULES_PRIORITY_WEIGHT = float(os.getenv("RULES_PRIORITY_WEIGHT", "0.65"))


class GenerationRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    asOf: date
    engineVersion: str | None = None
    ruleVersion: str | None = None


def url_for(name: str) -> str:
    value = os.getenv(f"{name.upper()}_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{name.upper()}_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def serialize(item: Opportunity) -> dict[str, Any]:
    return {
        "opportunityId": item.opportunity_ref,
        "customerId": item.customer_ref,
        "customerName": item.customer_name,
        "legalName": item.customer_name,
        "opportunityType": item.opportunity_type,
        "status": item.status,
        "confidence": float(item.confidence_score),
        "confidenceLevel": item.confidence_level,
        "priorityScore": float(item.priority_score),
        "priorityLevel": item.priority_level,
        "horizon": item.horizon,
        "why": item.why_json,
        "what": item.what_text,
        "when": item.when_text,
        "recommendedProducts": item.recommended_products_json,
        "evidenceCount": len(item.explanation_json.get("evidence", [])),
        "generatedAt": item.generated_at.isoformat(),
        "engineVersion": item.engine_version,
        "ruleVersion": item.rule_version,
        "lastActionAt": None,
    }


def find(item_id: str, session: Session) -> Opportunity:
    item = session.scalar(select(Opportunity).where(Opportunity.opportunity_ref == item_id))
    if item is None:
        raise not_found("Opportunity")
    return item


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
            "q",
            "customerId",
            "type",
            "opportunityType",
            "minConfidence",
            "maxConfidence",
            "priorityLevel",
            "sector",
            "customerSegment",
            "relationshipManagerId",
            "horizon",
            "fromDate",
            "toDate",
            "status",
            "sort",
        },
    )
    params = request.query_params
    offset = decode_cursor(cursor)
    stmt = select(Opportunity)
    target = customer_id or params.get("customerId")
    if target:
        stmt = stmt.where(Opportunity.customer_ref == target)
    opp_type = params.get("type") or params.get("opportunityType")
    if opp_type:
        stmt = stmt.where(Opportunity.opportunity_type == opp_type)
    if params.get("minConfidence"):
        stmt = stmt.where(Opportunity.confidence_score >= Decimal(params["minConfidence"]))
    if params.get("maxConfidence"):
        stmt = stmt.where(Opportunity.confidence_score <= Decimal(params["maxConfidence"]))
    if params.get("priorityLevel"):
        stmt = stmt.where(Opportunity.priority_level == params["priorityLevel"])
    if params.get("horizon"):
        stmt = stmt.where(Opportunity.horizon == params["horizon"])
    if params.get("status"):
        stmt = stmt.where(Opportunity.status == params["status"])
    if params.get("fromDate"):
        stmt = stmt.where(
            Opportunity.generated_at
            >= datetime.combine(
                date.fromisoformat(params["fromDate"]), time.min, tzinfo=timezone.utc
            )
        )
    if params.get("toDate"):
        stmt = stmt.where(
            Opportunity.generated_at
            < datetime.combine(date.fromisoformat(params["toDate"]), time.min, tzinfo=timezone.utc)
        )
    sort = params.get("sort", "-priorityScore")
    column = {
        "priorityScore": Opportunity.priority_score,
        "confidence": Opportunity.confidence_score,
        "generatedAt": Opportunity.generated_at,
        "opportunityType": Opportunity.opportunity_type,
    }.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported opportunity sort field.")
    rows = list(
        session.scalars(
            stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), Opportunity.id)
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
    f"{PREFIX}/opportunities",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Opportunities"],
)
def list_opportunities(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(request, session, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/opportunities",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Opportunities"],
)
def customer_opportunities(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 100,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(request, session, customer_id=customer_id, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Opportunities"],
)
def get_opportunity(opportunity_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return serialize(find(opportunity_id, session))


@app.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/explanation",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Opportunities"],
)
def get_explanation(opportunity_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return find(opportunity_id, session).explanation_json


def configured_rules(session: Session) -> RuleSetConfig:
    config = active_rule_set()
    # Ordre chronologique : si plusieurs lignes sont actives pour un même type, la plus
    # récente (clone créé par l'API d'administration) l'emporte de façon stable.
    rows = list(
        session.scalars(
            select(OpportunityRule)
            .where(OpportunityRule.active.is_(True))
            .order_by(OpportunityRule.created_at, OpportunityRule.version)
        )
    )
    if not rows:
        return config
    updates = {
        row.opportunity_type: OpportunityRuleConfig.model_validate(row.configuration_json)
        for row in rows
    }
    raw = config.model_dump(mode="python")
    raw["opportunity_rules"].update(
        {key: value.model_dump(mode="python") for key, value in updates.items()}
    )
    return RuleSetConfig.model_validate(raw)


def rule_engine_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    aliases = {
        "inflow_amount": "INFLOW_GROWTH",
        "supplier_payment_amount": "SUPPLIER_PAYMENT_GROWTH",
        "transaction_count": "TRANSACTION_VOLUME_GROWTH",
        "international_flow_amount": "INTERNATIONAL_FLOW_GROWTH",
        "average_balance": "BALANCE_SURPLUS",
        "credit_line_utilization": "CREDIT_UTILIZATION_INCREASE",
    }
    result: dict[str, Any] = {}
    for row in rows:
        code = str(row["metric"])
        period = str(row.get("period") or "")
        value = {
            "currentValue": row.get("currentValue"),
            "previousPeriodValue": row.get("previousPeriodValue"),
            "growthRate": row.get("growthRate"),
            "change": row.get("change"),
        }
        for metric_code in (code, aliases.get(code)):
            if not metric_code:
                continue
            metric_value: Any = value
            if metric_code.endswith("_GROWTH"):
                metric_value = value["growthRate"]
            elif metric_code == "CREDIT_UTILIZATION_INCREASE":
                metric_value = value["change"]
            result.setdefault(metric_code, metric_value)
            if period:
                result[f"{metric_code}:{period}"] = metric_value
    return result


_STUDIO_OPERATORS = {
    "INCREASE_BY": "gt",
    "DECREASE_BY": "gt",
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
    "=": "eq",
    "!=": "ne",
}


def evidence_label(item: dict[str, Any]) -> str:
    """Même forme que les explications du moteur (« X: observed=…, condition=gt … »)
    pour que la fiche PME et le dashboard chiffrent les signaux d'une règle publiée."""
    operator = _STUDIO_OPERATORS.get(str(item.get("operator") or ""), "configured")
    actual = item.get("actual")
    threshold = item.get("threshold")
    if actual is None or threshold is None or isinstance(actual, (list, dict)):
        return f"{item['metric']}: published rule condition satisfied"
    return f"{item['metric']}: observed={actual}, condition={operator} {threshold}"


def rule_engine_candidates(
    customer_id: str,
    as_of: date,
    response: dict[str, Any],
) -> list[OpportunityCandidate]:
    raw_matches = response.get("matches")
    matches = (
        raw_matches
        if isinstance(raw_matches, list)
        else [response]
        if response.get("matched")
        else []
    )
    candidates: list[OpportunityCandidate] = []
    for match in matches:
        evidence = tuple(
            ConditionEvidence(
                key=str(item["metric"]),
                operator=str(item.get("operator") or "configured"),
                expected=item.get("threshold"),
                observed=item.get("actual"),
                passed=bool(item.get("result")),
                label=evidence_label(item),
            )
            for item in match.get("evidence", [])
        )
        confidence = float(match.get("confidence") or 0)
        confidence_level: Literal["LOW", "MEDIUM", "HIGH"] = (
            "HIGH" if confidence >= 0.8 else "MEDIUM" if confidence >= 0.5 else "LOW"
        )
        priority_level: Literal["P1", "P2", "P3", "P4"] = (
            "P1" if confidence >= 0.8 else "P2" if confidence >= 0.5 else "P3"
        )
        rule_id = str(match["ruleId"])
        rule_version = str(match["ruleVersion"])
        opportunity_type = str(match["opportunityType"])
        candidates.append(
            OpportunityCandidate(
                opportunity_id=str(
                    deterministic_uuid(
                        "rule-studio-opportunity",
                        customer_id,
                        opportunity_type,
                        as_of,
                        rule_id,
                        rule_version,
                    )
                ),
                customer_id=customer_id,
                opportunity_type=opportunity_type,
                horizon=str(match.get("horizon") or "1-3_MONTHS"),
                confidence=confidence,
                confidence_level=confidence_level,
                confidence_components=(
                    {
                        "name": "published_rule_confidence",
                        "weighted_value": confidence,
                        "weight": 1,
                    },
                ),
                priority_score=confidence,
                priority_level=priority_level,
                priority_components=(
                    {"name": "rule_confidence", "weighted_value": confidence, "weight": 1},
                ),
                why=tuple(item.label for item in evidence if item.passed),
                what=(
                    f"Règle publiée « {match.get('ruleName') or rule_id} » (version "
                    f"{rule_version}) : opportunité à qualifier avec le client."
                ),
                when=HORIZON_LABELS.get(
                    str(match.get("horizon") or "1-3_MONTHS"),
                    str(match.get("horizon") or "1-3_MONTHS"),
                ),
                recommended_products=tuple(match.get("productCodes") or []),
                evidence=evidence,
                as_of_date=as_of,
                generated_at=datetime.now(timezone.utc).isoformat(),
                engine_version=str(match.get("engineVersion") or "rule-engine"),
                rule_version=f"{rule_id}:v{rule_version}",
                rule_set_version="rule-studio",
            )
        )
    return candidates


def rerank_with_propensity(
    candidate: OpportunityCandidate,
    propensity: dict[str, Any],
) -> OpportunityCandidate:
    raw_rules_score = float(candidate.priority_score)
    rules_score = raw_rules_score / 100 if raw_rules_score > 1 else raw_rules_score
    ml_score = min(1.0, max(0.0, float(propensity["propensity"])))
    denominator = ML_PRIORITY_WEIGHT + RULES_PRIORITY_WEIGHT
    combined = (
        (ML_PRIORITY_WEIGHT * ml_score + RULES_PRIORITY_WEIGHT * rules_score) / denominator
        if denominator > 0
        else rules_score
    )
    priority_level: Literal["P1", "P2", "P3", "P4"] = (
        "P1" if combined >= 0.8 else "P2" if combined >= 0.6 else "P3" if combined >= 0.4 else "P4"
    )
    ml_component = {
        "name": "sales_propensity_ml",
        "raw_value": ml_score,
        "normalized_value": ml_score,
        "weighted_value": ML_PRIORITY_WEIGHT * ml_score,
        "weight": ML_PRIORITY_WEIGHT,
        "model_version": propensity["modelVersion"],
        "feature_version": propensity["featureVersion"],
        "training_dataset_version": propensity["trainingDatasetVersion"],
        "deployment_mode": propensity["deploymentMode"],
        "trace_id": propensity["traceId"],
    }
    return candidate.model_copy(
        update={
            "priority_score": round(combined * 100, 4),
            "priority_level": priority_level,
            "priority_components": (*candidate.priority_components, ml_component),
            "why": (
                *candidate.why,
                f"Propension commerciale ML {ml_score:.2f} intégrée à la priorité de démonstration.",
            ),
            "engine_version": f"{candidate.engine_version}+ml-rerank-poc-v1",
        }
    )


async def context_for(
    customer_id: str, as_of: date, request: Request
) -> tuple[
    OpportunityContext,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
]:
    corr = correlation_id(request)
    auth = request.headers.get("Authorization")
    customer = await service_request(
        "GET",
        f"{url_for('customer')}/internal/v1/customers/{customer_id}",
        correlation_id=corr,
        incoming_authorization=auth,
    )
    metrics_page = await service_request(
        "GET",
        f"{url_for('analytics')}/internal/v1/customers/{customer_id}/metrics",
        correlation_id=corr,
        params={"pageSize": 1000},
        incoming_authorization=auth,
    )
    signals_page = await service_request(
        "GET",
        f"{url_for('signal')}/internal/v1/customers/{customer_id}/signals",
        correlation_id=corr,
        params={"pageSize": 1000},
        incoming_authorization=auth,
    )
    gaps = await service_request(
        "GET",
        f"{url_for('product')}/internal/v1/customers/{customer_id}/product-gaps",
        correlation_id=corr,
        incoming_authorization=auth,
    )
    metrics_90 = {row["metric"]: row for row in metrics_page["data"] if row["period"] == "90D"}

    def value(code: str, field: str, default: float = 0.0) -> float:
        item = metrics_90.get(code, {})
        raw = item.get(field)
        return default if raw is None else float(raw)

    def adjusted(code: str) -> bool:
        return bool(metrics_90.get(code, {}).get("seasonalityAdjusted"))

    product_status = family_status(gaps["gaps"])
    facts: dict[str, float | int | bool | str] = {
        "inflow_growth_rate": value("inflow_amount", "growthRate"),
        "inflow_growth_rate_seasonality_adjusted": adjusted("inflow_amount"),
        "supplier_payment_growth_rate": value("supplier_payment_amount", "growthRate"),
        "supplier_payment_growth_rate_seasonality_adjusted": adjusted("supplier_payment_amount"),
        "transaction_volume_growth_rate": value("transaction_count", "growthRate"),
        "transaction_volume_growth_rate_seasonality_adjusted": adjusted("transaction_count"),
        "no_recent_investment_financing": product_status.get("INVESTMENT_FINANCING")
        in {None, "ABSENT"},
        "international_flow_growth_rate": value("international_flow_amount", "growthRate"),
        "international_flow_growth_rate_seasonality_adjusted": adjusted(
            "international_flow_amount"
        ),
        "international_frequency_growth_rate": value(
            "international_transaction_count", "growthRate"
        ),
        "international_frequency_growth_rate_seasonality_adjusted": adjusted(
            "international_transaction_count"
        ),
        "international_frequency_confirmed": value(
            "international_transaction_count", "currentValue"
        )
        >= 12
        and value("international_transaction_count", "growthRate") >= 2
        and len(
            [
                row
                for row in metrics_page["data"]
                if row["metric"] == "international_transaction_count"
                and row["period"] in {"30D", "90D", "180D"}
                and (row.get("currentValue") or 0) >= 6
                and (row.get("growthRate") or 0) > 0
            ]
        )
        >= 2,
        "trade_finance_gap": product_status.get("TRADE_FINANCE")
        in {None, "ABSENT", "UNDERUTILIZED"},
        "average_balance": value("average_balance", "currentValue"),
        "average_balance_seasonality_adjusted": adjusted("average_balance"),
        "surplus_day_ratio": value("surplus_day_ratio", "currentValue"),
        "surplus_day_ratio_seasonality_adjusted": adjusted("surplus_day_ratio"),
        "surplus_persistence_periods": len(
            [
                row
                for row in metrics_page["data"]
                if row["metric"] == "surplus_day_ratio"
                and row["period"] in {"30D", "90D", "180D"}
                and (row.get("currentValue") or 0) >= 0.70
            ]
        ),
        "credit_line_utilization": value("credit_line_utilization", "currentValue"),
        "credit_line_utilization_seasonality_adjusted": adjusted("credit_line_utilization"),
        "credit_utilization_change": value("credit_line_utilization", "change"),
        "credit_utilization_change_seasonality_adjusted": adjusted("credit_line_utilization"),
        "balance_growth_rate": value("average_balance", "growthRate"),
        "balance_growth_rate_seasonality_adjusted": adjusted("average_balance"),
        "persistence_score": min(
            1.0,
            len([row for row in signals_page["data"] if row.get("status") == "CONFIRMED"]) / 3,
        ),
    }
    coverages = [float(row.get("dataCoverage") or 0) for row in metrics_90.values()]
    quality = min(coverages) if coverages else 0.0
    seasonality = bool(metrics_90)
    context = OpportunityContext(
        customer_id=customer_id,
        as_of_date=as_of,
        facts=facts,
        data_coverage=quality,
        data_quality="VALID" if quality >= 0.83 else "PARTIAL",
        seasonality_adjusted=seasonality,
        confidence_factors={},
        priority_factors={"relationship_context": 0.75},
    )
    catalog = {item["product"]["productId"]: item["product"] for item in gaps["gaps"]}
    return context, metrics_page["data"], signals_page["data"], catalog, customer


@app.post(
    f"{PREFIX}/opportunities/generate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Opportunities"],
)
async def generate(
    payload: GenerationRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    config = configured_rules(session)
    engine = OpportunityEngine(config)
    generated = 0
    audit_builder = DecisionAuditBuilder()
    for customer_id in payload.customerIds:
        context, metrics, signals, catalog, customer = await context_for(
            customer_id, payload.asOf, request
        )
        propensity = await service_request(
            "POST",
            f"{url_for('ml_engine')}/internal/v1/ml/customers/{customer_id}/score",
            correlation_id=correlation_id(request),
            json={"asOf": payload.asOf.isoformat()},
            incoming_authorization=request.headers.get("Authorization"),
        )
        published_response = await service_request(
            "POST",
            f"{url_for('rule_engine')}/internal/v1/rules/evaluate",
            correlation_id=correlation_id(request),
            json={"customerId": customer_id, "metrics": rule_engine_metrics(metrics)},
            incoming_authorization=request.headers.get("Authorization"),
        )
        published = rule_engine_candidates(customer_id, payload.asOf, published_response)
        # Une règle Rule Studio publiée remplace la règle moteur du même type : sinon la
        # PME recevrait deux opportunités identiques sous deux versions de règle.
        governed_types = {candidate.opportunity_type for candidate in published}
        candidates = [
            rerank_with_propensity(candidate, propensity)
            for candidate in [
                *(c for c in engine.evaluate(context) if c.opportunity_type not in governed_types),
                *published,
            ]
        ]
        for candidate in candidates:
            rule = session.scalar(
                select(OpportunityRule)
                .where(
                    OpportunityRule.opportunity_type == candidate.opportunity_type,
                    OpportunityRule.version == candidate.rule_version,
                    OpportunityRule.active.is_(True),
                )
                .order_by(OpportunityRule.created_at.desc())
            )
            if rule is None:
                rule = session.get(
                    OpportunityRule,
                    deterministic_uuid(
                        "opp-rule", candidate.opportunity_type, candidate.rule_version
                    ),
                )
            if rule is None:
                configured = config.opportunity_rules.get(candidate.opportunity_type)
                rule = OpportunityRule(
                    id=deterministic_uuid(
                        "opp-rule", candidate.opportunity_type, candidate.rule_version
                    ),
                    opportunity_type=candidate.opportunity_type,
                    version=candidate.rule_version,
                    configuration_json=(
                        configured.model_dump(mode="json")
                        if configured
                        else {
                            "source": "rule-studio",
                            "ruleVersion": candidate.rule_version,
                            "evidence": [
                                item.model_dump(mode="json") for item in candidate.evidence
                            ],
                        }
                    ),
                    active=True,
                    created_by="opportunity-service",
                )
                if candidate.rule_set_version == "rule-studio":
                    # Une nouvelle version publiée remplace les versions précédentes de la
                    # même règle Rule Studio dans le registre des règles moteur.
                    studio_prefix = candidate.rule_version.split(":v")[0] + ":v"
                    for previous in session.scalars(
                        select(OpportunityRule).where(
                            OpportunityRule.opportunity_type == candidate.opportunity_type,
                            OpportunityRule.active.is_(True),
                            OpportunityRule.version.like(f"{studio_prefix}%"),
                        )
                    ):
                        previous.active = False
                session.add(rule)
                session.flush()
            recommendations = [
                catalog[code] for code in candidate.recommended_products if code in catalog
            ]
            evidence = [item.model_dump(mode="json") for item in candidate.evidence]
            relevant_metrics = [
                row
                for row in metrics
                if row["period"] == "90D"
                and row["metric"]
                in {
                    "inflow_amount",
                    "supplier_payment_amount",
                    "transaction_count",
                    "international_flow_amount",
                    "international_transaction_count",
                    "average_balance",
                    "surplus_day_ratio",
                    "credit_line_utilization",
                }
            ]
            relevant_signals = [
                row for row in signals if row.get("status") in {"CONFIRMED", "OBSERVED"}
            ]
            confidence_components = [
                {
                    "name": item.get("name", "component"),
                    # Le moteur de confiance sérialise `points` (= weight * normalized_value).
                    "points": round(float(item.get("points", item.get("weighted_value", 0))), 2),
                    "maxPoints": round(float(item.get("weight", 0)), 2),
                    "satisfied": float(item.get("normalized_value", 0)) > 0,
                    "value": item.get("raw_value"),
                }
                for item in candidate.confidence_components
            ]
            configured = config.opportunity_rules.get(candidate.opportunity_type)
            thresholds = (
                {
                    item.key: item.value
                    for item in configured.all_conditions + configured.any_conditions
                }
                if configured
                else {item.key: item.expected for item in candidate.evidence}
            )
            explanation = {
                "opportunityId": candidate.opportunity_id,
                "signals": relevant_signals,
                "metrics": relevant_metrics or [row for row in metrics if row["period"] == "90D"],
                "thresholds": thresholds,
                "historicalComparison": {
                    "baselinePeriod": "365D",
                    "method": "previous_period_and_historical_baseline",
                },
                "confidenceComponents": confidence_components,
                "recommendedProducts": recommendations,
                "horizon": candidate.horizon,
                "engineVersion": candidate.engine_version,
                "ruleVersion": candidate.rule_version,
                "evidence": evidence,
                "audit": {
                    "ruleSetVersion": candidate.rule_set_version,
                    "correlationId": correlation_id(request),
                },
                "propensity": propensity,
                "combination": {
                    "method": "HYBRID_ML_RULES",
                    "mlWeight": ML_PRIORITY_WEIGHT,
                    "rulesWeight": RULES_PRIORITY_WEIGHT,
                    "commercialUseOnly": True,
                },
            }
            values = {
                "id": deterministic_uuid("opportunity-row", candidate.opportunity_id),
                "opportunity_ref": candidate.opportunity_id,
                "customer_id": deterministic_uuid("customer", customer_id),
                "customer_ref": customer_id,
                "customer_name": customer["legalName"],
                "opportunity_type": candidate.opportunity_type,
                "status": candidate.status,
                "horizon": candidate.horizon,
                "confidence_score": Decimal(str(candidate.confidence)),
                "confidence_level": candidate.confidence_level,
                "confidence_components_json": list(candidate.confidence_components),
                "priority_score": Decimal(str(candidate.priority_score)),
                "priority_level": candidate.priority_level,
                "priority_components_json": list(candidate.priority_components),
                "why_json": list(candidate.why),
                "what_text": candidate.what,
                "when_text": candidate.when,
                "recommended_products_json": recommendations,
                "explanation_json": explanation,
                "generated_at": datetime.combine(payload.asOf, time.min, tzinfo=timezone.utc),
                "engine_version": candidate.engine_version,
                "rule_version": candidate.rule_version,
                "rule_id": rule.id,
                "deduplication_key": (
                    f"{customer_id}:{candidate.opportunity_type}:"
                    f"{payload.asOf}:{candidate.rule_version}"
                ),
                "created_by": "opportunity-service",
            }
            session.execute(
                pg_insert(Opportunity)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[Opportunity.deduplication_key],
                    set_={
                        key: value
                        for key, value in values.items()
                        if key not in {"id", "deduplication_key", "created_by"}
                    },
                )
            )
            session.flush()
            opportunity_id = values["id"]
            for position, item in enumerate(candidate.evidence):
                observed = (
                    1
                    if item.observed is True
                    else 0
                    if item.observed is False
                    else item.observed
                    if isinstance(item.observed, (int, float))
                    else 0
                )
                threshold = (
                    1
                    if item.expected is True
                    else 0
                    if item.expected is False
                    else item.expected
                    if isinstance(item.expected, (int, float))
                    else 0
                )
                session.execute(
                    pg_insert(OpportunityEvidence)
                    .values(
                        id=deterministic_uuid(
                            "opportunity-evidence", candidate.opportunity_id, position
                        ),
                        opportunity_id=opportunity_id,
                        metric_code=item.key,
                        observed_value=Decimal(str(observed or 0)),
                        threshold=Decimal(str(threshold or 0)),
                        comparison_value=None,
                        why_text=item.label,
                        position=position,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            OpportunityEvidence.opportunity_id,
                            OpportunityEvidence.position,
                        ]
                    )
                )
            audit = audit_builder.build(
                decision_id=candidate.opportunity_id,
                opportunity={
                    "type": candidate.opportunity_type,
                    "what": candidate.what,
                },
                inputs={"metrics": metrics, "signals": signals, "propensity": propensity},
                config_id=config.config_id,
                config_checksum=config.checksum(),
                correlation_id=correlation_id(request),
            )
            session.execute(
                pg_insert(DecisionAudit)
                .values(
                    id=deterministic_uuid("decision-audit", audit["decision_hash"]),
                    opportunity_id=opportunity_id,
                    customer_id=deterministic_uuid("customer", customer_id),
                    engine_version=candidate.engine_version,
                    rule_version=candidate.rule_version,
                    generated_at=datetime.combine(payload.asOf, time.min, tzinfo=timezone.utc),
                    input_reference=f"metrics:{payload.asOf}",
                    signals_json=signals,
                    metric_snapshots_json=metrics,
                    confidence_components_json=list(candidate.confidence_components),
                    priority_components_json=list(candidate.priority_components),
                    decision_hash=audit["decision_hash"],
                )
                .on_conflict_do_nothing(index_elements=[DecisionAudit.decision_hash])
            )
            generated += 1
    return {
        "jobId": str(deterministic_uuid("opportunity-job", idempotency_key)),
        "status": "COMPLETED",
        "opportunities": generated,
        "customers": len(payload.customerIds),
        "asOf": payload.asOf.isoformat(),
        "ruleSetVersion": config.rule_set_version,
    }


@app.get(
    f"{PREFIX}/admin/rules",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Administration"],
)
def rules(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 100,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(OpportunityRule).order_by(
                OpportunityRule.opportunity_type, OpportunityRule.created_at.desc()
            )
        )
    )
    data = [
        {
            "ruleId": str(row.id),
            "name": row.opportunity_type.replace("_", " ").title(),
            "opportunityType": row.opportunity_type,
            "enabled": row.active,
            "version": row.version,
            "ruleVersion": row.version,
            "parameters": row.configuration_json,
        }
        for row in rows
    ]
    return page_response(
        request,
        data[: page_size + 1],
        page_size=page_size,
        offset=decode_cursor(cursor),
        total_count=len(data),
    )


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    parameters: dict[str, Any] | list[dict[str, Any]] | None = None
    justification: str = Field(min_length=3, max_length=1_000)
    effectiveAt: datetime | None = None


@app.patch(
    f"{PREFIX}/admin/rules/{{rule_id}}",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Administration"],
)
def update_rule(
    rule_id: str, payload: RuleUpdate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    try:
        parsed_rule_id = UUID(rule_id)
    except ValueError:
        raise not_found("Rule") from None
    row = session.get(OpportunityRule, parsed_rule_id)
    if row is None:
        raise not_found("Rule")
    version = f"{row.version}-v{int(datetime.now(timezone.utc).timestamp())}"
    configuration = dict(row.configuration_json)
    if isinstance(payload.parameters, dict):
        configuration.update(payload.parameters)
    # La version portée par la configuration doit suivre celle de la ligne : c'est elle
    # que le moteur attache aux opportunités et qu'il utilise pour retrouver la règle.
    configuration["version"] = version
    clone = OpportunityRule(
        id=deterministic_uuid("opp-rule", row.opportunity_type, version),
        opportunity_type=row.opportunity_type,
        version=version,
        configuration_json=configuration,
        active=payload.enabled if payload.enabled is not None else row.active,
        created_by="admin-api",
    )
    row.active = False
    session.add(clone)
    return {
        "ruleId": str(clone.id),
        "name": clone.opportunity_type.replace("_", " ").title(),
        "opportunityType": clone.opportunity_type,
        "enabled": clone.active,
        "version": clone.version,
        "ruleVersion": clone.version,
        "parameters": clone.configuration_json,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "updatedBy": "admin-api",
    }


@app.get(
    f"{PREFIX}/admin/engine",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Administration"],
)
def engine_info(session: Session = Depends(get_session)) -> dict[str, Any]:
    config = configured_rules(session)
    latest = session.scalar(select(func.max(Opportunity.generated_at)))
    return {
        "engineVersion": config.engine_version,
        "activeRuleVersion": config.rule_set_version,
        "ruleVersion": config.rule_set_version,
        "status": config.status,
        "lastRunAt": latest.isoformat() if latest else None,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


__all__ = ["app"]
