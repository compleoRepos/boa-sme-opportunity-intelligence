from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    Opportunity,
    ScoringPolicy,
    ScoringPolicyAuditLog,
    ScoringPolicyVersion,
)
from boa_oi.platform import (
    Principal,
    Problem,
    correlation_id,
    get_session,
    page_response,
    reject_unknown_filters,
    require_roles,
)
from boa_oi.scoring_policy.domain import PolicyStatus
from boa_oi.scoring_policy.service import (
    active_policy,
    audit_events,
    create_policy,
    create_version,
    find_policy,
    find_version,
    rollback_policy,
    serialize_policy,
    serialize_version,
    transition_policy,
)

router = APIRouter(prefix="/internal/v1/scoring-policies", tags=["Scoring policies"])
app_router = router
PREFIX = "/internal/v1/scoring-policies"
READ_ROLES = (
    "DATA_ANALYST",
    "BUSINESS_ANALYST",
    "ML_STEWARD",
    "RULE_APPROVER",
    "ADMIN",
    "SERVICE",
)
AUTHOR_ROLES = ("DATA_ANALYST", "BUSINESS_ANALYST", "ML_STEWARD", "ADMIN")
APPROVER_ROLES = ("RULE_APPROVER", "ADMIN")
PUBLISHER_ROLES = ("RULE_APPROVER", "ADMIN")
OPERATOR_ROLES = ("RULE_APPROVER", "ADMIN", "SERVICE")


class PolicyPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    policy_id: str = Field(alias="policyId", min_length=1, max_length=80)
    weights: dict[str, Any]
    reason: str = Field(min_length=1)


class VersionPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    weights: dict[str, Any]
    reason: str = Field(min_length=1)


class MutationPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    reason: str = Field(min_length=1)
    simulation_id: str | None = Field(default=None, alias="simulationId")
    effective_from: datetime | None = Field(default=None, alias="effectiveFrom")


class RollbackPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target_version: int = Field(alias="targetVersion", ge=1)
    reason: str = Field(min_length=1)


class SimulatePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    reason: str = Field(min_length=1)
    simulation_id: str | None = Field(default=None, alias="simulationId")


def _priority_level(score: float) -> str:
    return "P1" if score >= 80 else "P2" if score >= 60 else "P3" if score >= 40 else "P4"


def _simulate_portfolio(session: Session, row: ScoringPolicyVersion) -> dict[str, Any]:
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.status.in_(("OPEN", "ACCEPTED", "CONTACTED")))
            .order_by(Opportunity.generated_at.desc(), Opportunity.opportunity_ref)
            .limit(1_000)
        )
    )
    movements = {"up": 0, "down": 0, "unchanged": 0}
    before_distribution = dict.fromkeys(("P1", "P2", "P3", "P4"), 0)
    after_distribution = dict.fromkeys(("P1", "P2", "P3", "P4"), 0)
    changes: list[dict[str, Any]] = []
    skipped = 0
    ranks = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    rules_weight = float(row.rules_weight)
    ml_weight = float(row.ml_weight)
    for opportunity in opportunities:
        shadow = (opportunity.explanation_json or {}).get("propensityShadow")
        if not isinstance(shadow, dict) or shadow.get("deploymentMode") not in {
            None,
            "POC_SHADOW",
        }:
            skipped += 1
            continue
        score_value = shadow.get("propensity", shadow.get("score"))
        if score_value is None:
            skipped += 1
            continue
        try:
            ml_score = min(1.0, max(0.0, float(score_value)))
        except (TypeError, ValueError):
            skipped += 1
            continue
        rule_score = min(100.0, max(0.0, float(opportunity.priority_score)))
        simulated_score = round(
            min(100.0, max(0.0, rules_weight * rule_score + ml_weight * ml_score * 100)),
            4,
        )
        before_level = opportunity.priority_level
        after_level = _priority_level(simulated_score)
        before_distribution[before_level] += 1
        after_distribution[after_level] += 1
        direction = (
            "up"
            if ranks[after_level] < ranks[before_level]
            else "down"
            if ranks[after_level] > ranks[before_level]
            else "unchanged"
        )
        movements[direction] += 1
        changes.append(
            {
                "opportunityId": opportunity.opportunity_ref,
                "customerId": opportunity.customer_ref,
                "customerName": opportunity.customer_name,
                "beforeScore": round(rule_score, 4),
                "afterScore": simulated_score,
                "beforePriority": before_level,
                "afterPriority": after_level,
                "direction": direction,
                "absoluteDifference": round(abs(simulated_score - rule_score), 4),
                "contributions": [
                    {
                        "component": "RULES",
                        "rawScore": round(rule_score, 4),
                        "weight": rules_weight,
                        "weightedScore": round(rule_score * rules_weight, 4),
                    },
                    {
                        "component": "ML_SHADOW",
                        "rawScore": round(ml_score * 100, 4),
                        "weight": ml_weight,
                        "weightedScore": round(ml_score * 100 * ml_weight, 4),
                    },
                ],
            }
        )
    if not changes:
        raise Problem(
            409,
            "SIMULATION_DATA_UNAVAILABLE",
            "No active opportunity contains a persisted ML shadow score suitable for simulation.",
            details=[
                {
                    "activeOpportunities": len(opportunities),
                    "skippedWithoutShadowScore": skipped,
                }
            ],
        )
    changes.sort(key=lambda item: (-item["absoluteDifference"], item["opportunityId"]))
    return {
        "computedAt": datetime.now(timezone.utc).isoformat(),
        "source": "PERSISTED_OPPORTUNITIES_WITH_ML_SHADOW",
        "sampleCount": len(changes),
        "skippedWithoutShadowScore": skipped,
        "priorityDistribution": {
            "before": before_distribution,
            "after": after_distribution,
        },
        "movements": movements,
        "top10Changes": changes[:10],
        "limitations": [
            "POC_SHADOW_ONLY",
            "SYNTHETIC_DATA_NOT_PRODUCTION_PERFORMANCE",
            "NO_CREDIT_DECISION",
        ],
    }


def _actor(principal: Principal) -> str:
    return principal.username or principal.subject


def _trace(request: Request) -> str:
    value = request.headers.get("X-Correlation-ID", "").strip()
    if not value:
        raise Problem(400, "CORRELATION_ID_REQUIRED", "X-Correlation-ID is required for mutations.")
    return value


def _mutation_result(
    request: Request, row: ScoringPolicyVersion, policy_id: str | None = None
) -> dict[str, Any]:
    result = serialize_version(row, policy_id)
    result["correlationId"] = correlation_id(request)
    return result


@router.get("", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_policies(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    cursor: str | None = None,
    policy_status: Annotated[str | None, Query(alias="status")] = None,
    policy_id: Annotated[str | None, Query(alias="policyId")] = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"pageSize", "cursor", "status", "policyId"})
    stmt = select(ScoringPolicy)
    if policy_id:
        stmt = stmt.where(ScoringPolicy.policy_id == policy_id)
    if policy_status:
        stmt = stmt.join(
            ScoringPolicyVersion, ScoringPolicyVersion.policy_id == ScoringPolicy.id
        ).where(ScoringPolicyVersion.status == policy_status.upper())
    offset = 0
    if cursor:
        try:
            from boa_oi.platform import decode_cursor

            offset = decode_cursor(cursor)
        except Problem:
            raise
    rows = list(
        session.scalars(
            stmt.order_by(ScoringPolicy.updated_at.desc()).offset(offset).limit(page_size + 1)
        ).unique()
    )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return page_response(
        request,
        [serialize_policy(session, row) for row in rows],
        page_size=page_size,
        offset=offset,
        total_count=total,
    )


@router.get(
    "/active",
    dependencies=[
        Depends(
            require_roles(
                "SERVICE",
                "DATA_ANALYST",
                "BUSINESS_ANALYST",
                "ML_STEWARD",
                "RULE_APPROVER",
                "ADMIN",
            )
        )
    ],
)
def active(at: datetime | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = active_policy(session, at)
    if row is None:
        raise Problem(404, "ACTIVE_POLICY_NOT_FOUND", "No effective ACTIVE scoring policy exists.")
    policy = session.scalar(select(ScoringPolicy).where(ScoringPolicy.id == row.policy_id))
    return serialize_version(row, policy.policy_id if policy else None)


@router.get("/{policy_id}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_policy(policy_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return serialize_policy(session, find_policy(session, policy_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def post_policy(
    payload: PolicyPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    row = create_policy(
        session,
        payload.policy_id,
        payload.weights,
        _actor(principal),
        payload.reason,
        _trace(request),
    )
    session.flush()
    return serialize_policy(session, row)


@router.post("/{policy_id}/versions", status_code=status.HTTP_201_CREATED)
def post_version(
    policy_id: str,
    payload: VersionPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    row = create_version(
        session, policy_id, payload.weights, _actor(principal), payload.reason, _trace(request)
    )
    session.flush()
    return _mutation_result(request, row, policy_id)


@router.get("/{policy_id}/versions/{version}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_version(
    policy_id: str, version: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return serialize_version(find_version(session, policy_id, version), policy_id)


@router.get("/{policy_id}/versions", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_versions(policy_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    policy = find_policy(session, policy_id)
    rows = list(
        session.scalars(
            select(ScoringPolicyVersion)
            .where(ScoringPolicyVersion.policy_id == policy.id)
            .order_by(ScoringPolicyVersion.version)
        )
    )
    return {
        "data": [serialize_version(row, policy_id) for row in rows],
        "meta": {"pageSize": len(rows), "totalCount": len(rows), "hasMore": False},
    }


def _transition(
    policy_id: str,
    version: int,
    target: PolicyStatus,
    payload: MutationPayload,
    request: Request,
    session: Session,
    principal: Principal,
) -> dict[str, Any]:
    row = transition_policy(
        session,
        policy_id,
        version,
        target,
        _actor(principal),
        payload.reason,
        _trace(request),
        simulation_id=payload.simulation_id,
        effective_from=payload.effective_from,
    )
    session.flush()
    return _mutation_result(request, row, policy_id)


@router.post("/{policy_id}/versions/{version}/simulate", status_code=status.HTTP_202_ACCEPTED)
def simulate(
    policy_id: str,
    version: int,
    payload: SimulatePayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    policy_version = find_version(session, policy_id, version)
    simulation = _simulate_portfolio(session, policy_version)
    row = transition_policy(
        session,
        policy_id,
        version,
        PolicyStatus.SIMULATED,
        _actor(principal),
        payload.reason,
        _trace(request),
        simulation_id=payload.simulation_id,
    )
    session.flush()
    audit_row = session.scalar(
        select(ScoringPolicyAuditLog)
        .where(
            ScoringPolicyAuditLog.policy_id == row.policy_id,
            ScoringPolicyAuditLog.policy_version == version,
            ScoringPolicyAuditLog.action == "SIMULATED",
        )
        .order_by(ScoringPolicyAuditLog.timestamp.desc())
        .limit(1)
    )
    if audit_row is None:
        raise Problem(500, "SIMULATION_AUDIT_MISSING", "Simulation audit persistence failed.")
    audit_row.new_value_json = {
        **(audit_row.new_value_json or {}),
        "simulation": simulation,
    }
    session.flush()
    result = _mutation_result(request, row, policy_id)
    result["simulation"] = simulation
    return result


@router.post("/{policy_id}/versions/{version}/submit")
def submit(
    policy_id: str,
    version: int,
    payload: MutationPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    return _transition(
        policy_id, version, PolicyStatus.SUBMITTED, payload, request, session, principal
    )


@router.post("/{policy_id}/versions/{version}/approve")
def approve(
    policy_id: str,
    version: int,
    payload: MutationPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*APPROVER_ROLES)),
) -> dict[str, Any]:
    return _transition(
        policy_id, version, PolicyStatus.APPROVED, payload, request, session, principal
    )


@router.post("/{policy_id}/versions/{version}/publish")
def publish(
    policy_id: str,
    version: int,
    payload: MutationPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*PUBLISHER_ROLES)),
) -> dict[str, Any]:
    return _transition(
        policy_id, version, PolicyStatus.PUBLISHED, payload, request, session, principal
    )


@router.post("/{policy_id}/versions/{version}/activate")
def activate(
    policy_id: str,
    version: int,
    payload: MutationPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles("ADMIN", "SERVICE")),
) -> dict[str, Any]:
    return _transition(
        policy_id, version, PolicyStatus.ACTIVE, payload, request, session, principal
    )


@router.post("/{policy_id}/versions/{version}/disable")
def disable(
    policy_id: str,
    version: int,
    payload: MutationPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*OPERATOR_ROLES)),
) -> dict[str, Any]:
    return _transition(
        policy_id, version, PolicyStatus.DISABLED, payload, request, session, principal
    )


@router.post("/{policy_id}/rollback")
def rollback(
    policy_id: str,
    payload: RollbackPayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*OPERATOR_ROLES)),
) -> dict[str, Any]:
    row = rollback_policy(
        session,
        policy_id,
        payload.target_version,
        _actor(principal),
        payload.reason,
        _trace(request),
    )
    session.flush()
    return _mutation_result(request, row, policy_id)


@router.get("/{policy_id}/audit", dependencies=[Depends(require_roles(*READ_ROLES))])
def audit(policy_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    events = audit_events(session, policy_id)
    return {
        "data": events,
        "meta": {"pageSize": len(events), "totalCount": len(events), "hasMore": False},
    }


__all__ = ["app_router", "router"]
