from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    Customer,
    Opportunity,
    OpportunityAction,
    PropensityScoreRecord,
    RelationshipManager,
)
from boa_oi.platform import (
    Principal,
    Problem,
    create_service_app,
    current_principal,
    get_session,
    not_found,
    require_roles,
)

app = create_service_app(
    "portfolio-service",
    "Scoped commercial dashboards and explainable SME sales propensity read model.",
)
PREFIX = "/internal/v1"
RM_ROLES = ("RELATIONSHIP_MANAGER",)
BRANCH_ROLES = ("BRANCH_MANAGER",)
COMMERCIAL_READ_ROLES = ("RELATIONSHIP_MANAGER", "BRANCH_MANAGER", "ADMIN", "SERVICE")
ML_WEIGHT = float(os.getenv("ML_PRIORITY_WEIGHT", "0.35"))
RULES_WEIGHT = float(os.getenv("RULES_PRIORITY_WEIGHT", "0.65"))

FEATURE_LABELS = {
    "cash_inflow_growth_90d": "Croissance des encaissements sur 90 jours",
    "supplier_payment_growth_90d": "Dynamique des paiements fournisseurs sur 90 jours",
    "international_activity_ratio_90d": "Part de l’activité internationale sur 90 jours",
    "balance_strength_90d": "Solidité de la trésorerie observée sur 90 jours",
    "activity_density_90d": "Densité d’activité transactionnelle sur 90 jours",
    "analytics_coverage_90d": "Couverture des données analytiques",
    "customer_tenure_ratio": "Ancienneté de la relation PME",
    "segment_medium": "Appartenance au segment PME intermédiaire",
}


def _customer_scope(principal: Principal) -> tuple[tuple[str, ...] | None, tuple[str, ...] | None]:
    if {"ADMIN", "SERVICE"} & principal.roles:
        return None, None
    if "RELATIONSHIP_MANAGER" in principal.roles:
        if not principal.relationship_manager_ids:
            raise Problem(403, "PORTFOLIO_SCOPE_MISSING", "No relationship-manager scope is assigned.")
        return principal.relationship_manager_ids, None
    if "BRANCH_MANAGER" in principal.roles:
        if not principal.branch_ids:
            raise Problem(403, "PORTFOLIO_SCOPE_MISSING", "No branch scope is assigned.")
        return None, principal.branch_ids
    return None, None


def _scoped_customers(
    principal: Principal,
    *,
    relationship_manager_id: str | None = None,
) -> Select[tuple[Customer, RelationshipManager]]:
    rm_ids, branch_ids = _customer_scope(principal)
    stmt = select(Customer, RelationshipManager).join(
        RelationshipManager,
        Customer.rm_id == RelationshipManager.id,
    )
    if rm_ids:
        stmt = stmt.where(RelationshipManager.subject_id.in_(rm_ids))
    if branch_ids:
        stmt = stmt.where(RelationshipManager.branch_code.in_(branch_ids))
    if relationship_manager_id:
        stmt = stmt.where(RelationshipManager.subject_id == relationship_manager_id)
    return stmt.where(Customer.status == "ACTIVE").order_by(Customer.customer_ref)


def _rows(
    session: Session,
    principal: Principal,
    *,
    relationship_manager_id: str | None = None,
) -> list[tuple[Customer, RelationshipManager]]:
    return list(
        session.execute(
            _scoped_customers(
                principal,
                relationship_manager_id=relationship_manager_id,
            )
        ).tuples()
    )


def _latest_scores(session: Session, customer_ids: list[Any]) -> dict[Any, PropensityScoreRecord]:
    if not customer_ids:
        return {}
    ranked = (
        select(
            PropensityScoreRecord.id.label("id"),
            func.row_number()
            .over(
                partition_by=PropensityScoreRecord.customer_id,
                order_by=(
                    PropensityScoreRecord.as_of_date.desc(),
                    PropensityScoreRecord.created_at.desc(),
                ),
            )
            .label("position"),
        )
        .where(PropensityScoreRecord.customer_id.in_(customer_ids))
        .subquery()
    )
    records = session.scalars(
        select(PropensityScoreRecord)
        .join(ranked, PropensityScoreRecord.id == ranked.c.id)
        .where(ranked.c.position == 1)
    )
    return {record.customer_id: record for record in records}


def _opportunities(session: Session, customer_ids: list[Any]) -> dict[Any, list[Opportunity]]:
    result: dict[Any, list[Opportunity]] = {customer_id: [] for customer_id in customer_ids}
    if not customer_ids:
        return result
    records = session.scalars(
        select(Opportunity)
        .where(
            Opportunity.customer_id.in_(customer_ids),
            Opportunity.status.in_(("OPEN", "ACCEPTED", "CONTACTED")),
        )
        .order_by(Opportunity.priority_score.desc(), Opportunity.generated_at.desc())
    )
    for record in records:
        result.setdefault(record.customer_id, []).append(record)
    return result


def _actions(session: Session, customer_ids: list[Any]) -> dict[Any, list[OpportunityAction]]:
    result: dict[Any, list[OpportunityAction]] = {customer_id: [] for customer_id in customer_ids}
    if not customer_ids:
        return result
    records = session.scalars(
        select(OpportunityAction)
        .where(OpportunityAction.customer_id.in_(customer_ids))
        .order_by(
            OpportunityAction.due_at.asc().nulls_last(),
            OpportunityAction.created_at.desc(),
        )
    )
    for record in records:
        result.setdefault(record.customer_id, []).append(record)
    return result


def _normalized_rules_score(opportunities: list[Opportunity]) -> float:
    if not opportunities:
        return 0.0
    value = max(float(item.priority_score) for item in opportunities)
    return min(1.0, max(0.0, value / 100 if value > 1 else value))


def _combined_priority(propensity: float, rules_score: float) -> tuple[float, str]:
    denominator = ML_WEIGHT + RULES_WEIGHT
    combined = (
        (ML_WEIGHT * propensity + RULES_WEIGHT * rules_score) / denominator
        if denominator > 0
        else propensity
    )
    if combined >= 0.80:
        level = "P1"
    elif combined >= 0.60:
        level = "P2"
    elif combined >= 0.40:
        level = "P3"
    else:
        level = "P4"
    return combined, level


def _factor_label(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature.replace("_", " ").capitalize())


def _portfolio_payload(
    session: Session,
    rows: list[tuple[Customer, RelationshipManager]],
) -> dict[str, Any]:
    customer_ids = [customer.id for customer, _manager in rows]
    scores = _latest_scores(session, customer_ids)
    opportunities = _opportunities(session, customer_ids)
    actions = _actions(session, customer_ids)
    now = datetime.now(timezone.utc)
    due_limit = now + timedelta(days=7)
    portfolio: list[dict[str, Any]] = []
    distribution: Counter[str] = Counter()
    converted = 0
    contacted = 0
    all_open_opportunities = 0
    due_actions = 0
    for customer, manager in rows:
        score_record = scores.get(customer.id)
        propensity = float(score_record.score) if score_record else 0.0
        customer_opportunities = opportunities.get(customer.id, [])
        customer_actions = actions.get(customer.id, [])
        rules_score = _normalized_rules_score(customer_opportunities)
        combined, priority_level = _combined_priority(propensity, rules_score)
        distribution[priority_level] += 1
        open_actions = [item for item in customer_actions if item.status not in {"DONE", "CANCELLED"}]
        due_actions += sum(
            1 for item in open_actions if item.due_at is not None and item.due_at <= due_limit
        )
        converted += sum(1 for item in customer_actions if item.outcome_type == "CONVERTED")
        contacted += sum(
            1
            for item in customer_actions
            if item.outcome_type in {"CONTACTED", "MEETING_SCHEDULED", "OFFER_CREATED", "CONVERTED"}
        )
        all_open_opportunities += len(customer_opportunities)
        top_factor = (score_record.top_factors_json[0] if score_record and score_record.top_factors_json else None)
        portfolio.append(
            {
                "customerId": customer.customer_ref,
                "customerName": customer.legal_name,
                "industry": customer.sector_code,
                "relationshipManagerId": manager.subject_id,
                "relationshipManagerName": manager.display_name,
                "branchId": manager.branch_code,
                "propensityScore": propensity,
                "combinedPriorityScore": combined,
                "priorityLevel": priority_level,
                "priorityReason": (
                    f"{_factor_label(str(top_factor['feature']))} est le principal facteur du score."
                    if top_factor
                    else "Aucun score de propension matérialisé pour cette date."
                ),
                "openOpportunities": [
                    {
                        "opportunityId": item.opportunity_ref,
                        "opportunityType": item.opportunity_type,
                        "confidence": float(item.confidence_score),
                        "horizon": item.horizon,
                        "status": item.status,
                    }
                    for item in customer_opportunities[:3]
                ],
                "nextActions": [
                    {
                        "actionId": item.action_ref,
                        "opportunityId": item.opportunity_ref,
                        "actionType": item.action_type,
                        "dueAt": item.due_at.isoformat() if item.due_at else None,
                        "status": item.status,
                        "note": item.notes_redacted,
                    }
                    for item in open_actions[:3]
                ],
            }
        )
    portfolio.sort(
        key=lambda item: (
            -float(item["combinedPriorityScore"]),
            -float(item["propensityScore"]),
            str(item["customerId"]),
        )
    )
    total = len(rows)
    distribution_payload = [
        {
            "priorityLevel": level,
            "count": distribution[level],
            "share": distribution[level] / total if total else 0.0,
        }
        for level in ("P1", "P2", "P3", "P4")
    ]
    return {
        "portfolio": portfolio,
        "priorityDistribution": distribution_payload,
        "kpis": {
            "portfolioCustomers": total,
            "highPriorityCustomers": distribution["P1"],
            "openOpportunities": all_open_opportunities,
            "actionsDue": due_actions,
            "contactedCustomers": contacted,
            "convertedOpportunities": converted,
            "conversionRate": converted / contacted if contacted else 0.0,
        },
    }


@app.get(
    f"{PREFIX}/dashboards/me",
    dependencies=[Depends(require_roles(*RM_ROLES))],
    tags=["Commercial dashboards"],
)
def relationship_manager_dashboard(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = _rows(session, principal)
    payload = _portfolio_payload(session, rows)
    manager = rows[0][1] if rows else None
    payload.update(
        scope={
            "type": "RELATIONSHIP_MANAGER",
            "relationshipManagerId": (
                manager.subject_id if manager else principal.relationship_manager_ids[0]
            ),
            "relationshipManagerName": manager.display_name if manager else principal.username,
            "branchId": manager.branch_code if manager else None,
            "branchName": manager.branch_code if manager else None,
        },
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
    return payload


@app.get(
    f"{PREFIX}/dashboards/branch",
    dependencies=[Depends(require_roles(*BRANCH_ROLES))],
    tags=["Commercial dashboards"],
)
def branch_dashboard(
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = _rows(session, principal)
    payload = _portfolio_payload(session, rows)
    managers: list[dict[str, Any]] = []
    for manager_id in sorted({manager.subject_id for _customer, manager in rows}):
        manager_rows = [item for item in rows if item[1].subject_id == manager_id]
        manager_payload = _portfolio_payload(session, manager_rows)
        manager = manager_rows[0][1]
        kpis = manager_payload["kpis"]
        scores = [float(item["propensityScore"]) for item in manager_payload["portfolio"]]
        managers.append(
            {
                "relationshipManagerId": manager.subject_id,
                "relationshipManagerName": manager.display_name,
                **kpis,
                "averagePropensity": sum(scores) / len(scores) if scores else 0.0,
            }
        )
    actions = _actions(session, [customer.id for customer, _manager in rows])
    all_actions = [action for customer_actions in actions.values() for action in customer_actions]
    contacted = sum(
        1
        for item in all_actions
        if item.outcome_type in {"CONTACTED", "MEETING_SCHEDULED", "OFFER_CREATED", "CONVERTED"}
    )
    stages = [
        ("CONTACTED", contacted),
        ("MEETING_SCHEDULED", sum(1 for item in all_actions if item.outcome_type in {"MEETING_SCHEDULED", "OFFER_CREATED", "CONVERTED"})),
        ("OFFER_CREATED", sum(1 for item in all_actions if item.outcome_type in {"OFFER_CREATED", "CONVERTED"})),
        ("CONVERTED", sum(1 for item in all_actions if item.outcome_type == "CONVERTED")),
    ]
    branch_id = rows[0][1].branch_code if rows else principal.branch_ids[0]
    payload.pop("portfolio", None)
    payload.update(
        scope={"type": "BRANCH", "branchId": branch_id, "branchName": branch_id},
        relationshipManagers=managers,
        conversionFunnel=[
            {"stage": stage, "count": count, "rate": count / contacted if contacted else 0.0}
            for stage, count in stages
        ],
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
    return payload


@app.get(
    f"{PREFIX}/dashboards/relationship-managers/{{relationship_manager_id}}",
    dependencies=[Depends(require_roles(*BRANCH_ROLES))],
    tags=["Commercial dashboards"],
)
def relationship_manager_portfolio(
    relationship_manager_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = _rows(session, principal, relationship_manager_id=relationship_manager_id)
    if not rows:
        raise not_found("Relationship-manager portfolio")
    payload = _portfolio_payload(session, rows)
    manager = rows[0][1]
    payload.update(
        scope={
            "type": "RELATIONSHIP_MANAGER",
            "relationshipManagerId": manager.subject_id,
            "relationshipManagerName": manager.display_name,
            "branchId": manager.branch_code,
            "branchName": manager.branch_code,
        },
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
    return payload


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/propensity",
    dependencies=[Depends(require_roles(*COMMERCIAL_READ_ROLES))],
    tags=["Commercial propensity"],
)
def customer_propensity(
    customer_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.execute(
        _scoped_customers(principal).where(Customer.customer_ref == customer_id)
    ).first()
    if row is None:
        raise not_found("Customer")
    customer, _manager = row
    score_record = _latest_scores(session, [customer.id]).get(customer.id)
    if score_record is None:
        raise Problem(404, "PROPENSITY_NOT_SCORED", "No propensity score is available for this SME.")
    opportunities = _opportunities(session, [customer.id]).get(customer.id, [])
    rules_score = _normalized_rules_score(opportunities)
    propensity = float(score_record.score)
    combined, priority_level = _combined_priority(propensity, rules_score)
    factors = [
        {
            "feature": item["feature"],
            "label": _factor_label(str(item["feature"])),
            "value": item.get("value"),
            "direction": item.get("direction", "NEUTRAL"),
            "contribution": item.get("contribution"),
            "explanation": (
                f"Contribution {item.get('direction', 'NEUTRAL').lower()} au score de propension commerciale."
            ),
            "source": "Feature Store / Analytics",
        }
        for item in score_record.top_factors_json
    ]
    return {
        "customerId": customer.customer_ref,
        "score": propensity,
        "scoreMeaning": "intérêt commercial estimé",
        "priorityLevel": priority_level,
        "model": {
            "modelId": "sales-propensity-logistic",
            "modelVersion": score_record.model_version,
            "featureSetVersion": score_record.feature_set_version,
            "scoredAt": score_record.created_at.isoformat(),
        },
        "combination": {
            "method": "HYBRID_ML_RULES",
            "mlScore": propensity,
            "rulesScore": rules_score,
            "mlWeight": ML_WEIGHT,
            "rulesWeight": RULES_WEIGHT,
            "combinedPriorityScore": combined,
            "summary": "La propension ML complète les règles métier publiées pour ordonner le travail commercial.",
        },
        "factors": factors,
        "warnings": [
            "Aucune décision de crédit : ce score sert uniquement à prioriser une action commerciale.",
            "Le signal de tension financière, lorsqu’il existe, doit être examiné par un collaborateur.",
        ],
        "correlationId": getattr(request.state, "correlation_id", None),
    }


__all__ = ["app"]
