from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import ScoringPolicy, ScoringPolicyVersion
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
READ_ROLES = ("DATA_ANALYST", "BUSINESS_ANALYST", "RULE_APPROVER", "ADMIN", "SERVICE")
AUTHOR_ROLES = ("DATA_ANALYST", "BUSINESS_ANALYST", "ADMIN")
APPROVER_ROLES = ("RULE_APPROVER", "ADMIN")
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
    sample: dict[str, Any] = Field(default_factory=dict)


def _actor(principal: Principal) -> str:
    return principal.username or principal.subject


def _trace(request: Request) -> str:
    value = request.headers.get("X-Correlation-ID", "").strip()
    if not value:
        raise Problem(400, "CORRELATION_ID_REQUIRED", "X-Correlation-ID is required for mutations.")
    return value


def _mutation_result(request: Request, row: ScoringPolicyVersion) -> dict[str, Any]:
    result = serialize_version(row)
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
            require_roles("SERVICE", "DATA_ANALYST", "BUSINESS_ANALYST", "RULE_APPROVER", "ADMIN")
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
    return _mutation_result(request, row)


@router.get("/{policy_id}/versions/{version}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_version(
    policy_id: str, version: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return serialize_version(find_version(session, policy_id, version))


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
        "data": [serialize_version(row) for row in rows],
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
    return _mutation_result(request, row)


@router.post("/{policy_id}/versions/{version}/simulate", status_code=status.HTTP_202_ACCEPTED)
def simulate(
    policy_id: str,
    version: int,
    payload: SimulatePayload,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    mutation = MutationPayload(reason=payload.reason, simulationId=payload.simulation_id)
    result = _transition(
        policy_id, version, PolicyStatus.SIMULATED, mutation, request, session, principal
    )
    result["simulationId"] = result.get("simulationId") or payload.simulation_id
    result["sample"] = payload.sample
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
    principal: Principal = Depends(require_roles(*OPERATOR_ROLES)),
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
    principal: Principal = Depends(require_roles(*OPERATOR_ROLES)),
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
    return _mutation_result(request, row)


@router.get("/{policy_id}/audit", dependencies=[Depends(require_roles(*READ_ROLES))])
def audit(policy_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    events = audit_events(session, policy_id)
    return {
        "data": events,
        "meta": {"pageSize": len(events), "totalCount": len(events), "hasMore": False},
    }


__all__ = ["app_router", "router"]
