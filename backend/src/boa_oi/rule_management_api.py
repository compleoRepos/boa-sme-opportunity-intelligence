from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import Customer, MetricSnapshot, Rule, RuleAuditLog, RuleVersion
from boa_oi.platform import (
    Principal,
    create_service_app,
    decode_cursor,
    get_session,
    not_found,
    page_response,
    reject_unknown_filters,
    require_roles,
)
from boa_oi.rules import ENGINE_VERSION, RuleEvaluator
from boa_oi.rules.schemas import (
    DuplicateRequest,
    RollbackRequest,
    RuleDefinition,
    TransitionRequest,
)
from boa_oi.rules.service import (
    create_rule,
    duplicate_rule,
    find_rule,
    latest_version,
    rollback_rule,
    serialize_rule,
    serialize_version,
    transition,
    update_rule,
)
from boa_oi.rules.simulation import metric_payload

app = create_service_app(
    "rule-management-service",
    "Versioned Rule Studio management, validation, approval, publication and immutable history.",
)
PREFIX = "/internal/v1/rules"
RULE_READ_ROLES = (
    "BUSINESS_ANALYST",
    "RULE_APPROVER",
    "ADMIN",
    "SERVICE",
    "DATA_ANALYST",
)
RULE_AUTHOR_ROLES = ("BUSINESS_ANALYST", "ADMIN", "SERVICE")
RULE_APPROVER_ROLES = ("RULE_APPROVER", "ADMIN", "SERVICE")


def _principal(principal: Principal) -> str:
    return principal.username or principal.subject


def _page(data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {"pageSize": len(data), "hasMore": False, "totalCount": len(data)},
    }


@app.get(PREFIX, dependencies=[Depends(require_roles(*RULE_READ_ROLES))], tags=["Rules"])
def list_rules(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    cursor: str | None = None,
    rule_status: Annotated[str | None, Query(alias="status")] = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"pageSize", "cursor", "status", "q", "sort"})
    offset = decode_cursor(cursor)
    stmt = select(Rule)
    if rule_status:
        stmt = stmt.where(Rule.status == rule_status.upper())
    if q:
        stmt = stmt.where(Rule.name.ilike(f"%{q}%"))
    rows = list(
        session.scalars(
            stmt.order_by(Rule.updated_at.desc(), Rule.rule_id).offset(offset).limit(page_size + 1)
        )
    )
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    return page_response(
        request,
        [serialize_rule(session, item) for item in rows],
        page_size=page_size,
        offset=offset,
        total_count=total,
    )


@app.get(
    f"{PREFIX}/{{rule_id}}",
    dependencies=[Depends(require_roles(*RULE_READ_ROLES))],
    tags=["Rules"],
)
def get_rule(rule_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return serialize_rule(session, find_rule(session, rule_id))


@app.post(PREFIX, status_code=status.HTTP_201_CREATED, tags=["Rules"])
def post_rule(
    payload: RuleDefinition,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> dict[str, Any]:
    rule = create_rule(session, payload.model_dump(exclude_none=True), _principal(principal))
    session.flush()
    return serialize_rule(session, rule)


@app.put(f"{PREFIX}/{{rule_id}}", tags=["Rules"])
def put_rule(
    rule_id: str,
    payload: RuleDefinition,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> dict[str, Any]:
    rule = update_rule(
        session,
        rule_id,
        payload.model_dump(exclude_none=True),
        _principal(principal),
    )
    session.flush()
    return serialize_rule(session, rule)


@app.post(
    f"{PREFIX}/{{rule_id}}/duplicate",
    status_code=status.HTTP_201_CREATED,
    tags=["Rules"],
)
def duplicate(
    rule_id: str,
    payload: DuplicateRequest,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> dict[str, Any]:
    rule = duplicate_rule(
        session,
        rule_id,
        payload.name,
        _principal(principal),
        payload.reason,
    )
    session.flush()
    return serialize_rule(session, rule)


@app.post(f"{PREFIX}/{{rule_id}}/validate", tags=["Lifecycle"])
def validate(
    rule_id: str,
    payload: TransitionRequest | None = None,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> dict[str, Any]:
    rule = transition(
        session,
        rule_id,
        "validate",
        _principal(principal),
        reason=payload.reason if payload else None,
    )
    session.flush()
    return {
        "valid": True,
        "errors": [],
        "warnings": [],
        "rule": serialize_rule(session, rule),
    }


@app.post(f"{PREFIX}/{{rule_id}}/test", tags=["Rule Tester"])
def test_rule(
    rule_id: str,
    payload: dict[str, str],
    session: Session = Depends(get_session),
    _principal: Principal = Depends(require_roles(*RULE_READ_ROLES)),
) -> dict[str, Any]:
    customer_ref = payload.get("customerId", "")
    customer = session.scalar(select(Customer).where(Customer.customer_ref == customer_ref))
    if customer is None:
        raise not_found("Customer")
    rule = find_rule(session, rule_id)
    version = latest_version(session, rule)
    snapshots = list(
        session.scalars(
            select(MetricSnapshot)
            .where(MetricSnapshot.customer_id == customer.id)
            .order_by(MetricSnapshot.as_of_date.desc(), MetricSnapshot.window_days)
        )
    )
    metrics: dict[str, Any] = {}
    for snapshot in snapshots:
        for code, value in metric_payload(snapshot.values_json).items():
            metrics.setdefault(code, value)
            metrics[f"{code}:{snapshot.window_days}D"] = value
    evaluation = RuleEvaluator().evaluate(version.configuration_json, metrics)
    recommendation = version.configuration_json["recommendation"]
    return {
        "matched": evaluation.matched,
        "ruleId": rule.rule_id,
        "ruleVersion": version.version,
        "engineVersion": ENGINE_VERSION,
        "customerId": customer.customer_ref,
        "customerName": customer.legal_name,
        "opportunityType": recommendation["opportunityType"],
        "confidence": evaluation.confidence,
        "evidence": evaluation.evidence,
        "explanation": evaluation.explanation,
    }


@app.post(f"{PREFIX}/{{rule_id}}/submit", tags=["Lifecycle"])
def submit_rule(
    rule_id: str,
    payload: TransitionRequest | None = None,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> dict[str, Any]:
    rule = transition(
        session,
        rule_id,
        "submit",
        _principal(principal),
        reason=payload.reason if payload else None,
    )
    session.flush()
    return serialize_rule(session, rule)


@app.post(f"{PREFIX}/{{rule_id}}/approve", tags=["Lifecycle"])
def approve_rule(
    rule_id: str,
    payload: TransitionRequest | None = None,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_APPROVER_ROLES)),
) -> dict[str, Any]:
    rule = transition(
        session,
        rule_id,
        "approve",
        _principal(principal),
        reason=payload.reason if payload else None,
    )
    session.flush()
    return serialize_rule(session, rule)


@app.post(f"{PREFIX}/{{rule_id}}/publish", tags=["Lifecycle"])
def publish_rule(
    rule_id: str,
    payload: TransitionRequest | None = None,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_APPROVER_ROLES)),
) -> dict[str, Any]:
    reason = payload.reason if payload else None
    actor = _principal(principal)
    rule = transition(session, rule_id, "publish", actor, reason=reason)
    rule = transition(session, rule_id, "activate", actor, reason=reason)
    session.flush()
    return serialize_rule(session, rule)


@app.post(f"{PREFIX}/{{rule_id}}/rollback", tags=["Lifecycle"])
def rollback(
    rule_id: str,
    payload: RollbackRequest,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_APPROVER_ROLES)),
) -> dict[str, Any]:
    rule = rollback_rule(
        session,
        rule_id,
        _principal(principal),
        target_version=payload.version,
        reason=payload.reason,
    )
    session.flush()
    return serialize_rule(session, rule)


@app.post(f"{PREFIX}/{{rule_id}}/disable", tags=["Lifecycle"])
def disable(
    rule_id: str,
    payload: TransitionRequest | None = None,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*RULE_APPROVER_ROLES)),
) -> dict[str, Any]:
    rule = transition(
        session,
        rule_id,
        "disable",
        _principal(principal),
        reason=payload.reason if payload else None,
    )
    session.flush()
    return serialize_rule(session, rule)


@app.get(
    f"{PREFIX}/{{rule_id}}/versions",
    dependencies=[Depends(require_roles(*RULE_READ_ROLES))],
    tags=["History"],
)
def versions(rule_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    rule = find_rule(session, rule_id)
    rows = list(
        session.scalars(
            select(RuleVersion)
            .where(RuleVersion.rule_id == rule.id)
            .order_by(RuleVersion.version.desc())
        )
    )
    return _page([serialize_version(item) for item in rows])


@app.get(
    f"{PREFIX}/{{rule_id}}/history",
    dependencies=[Depends(require_roles(*RULE_READ_ROLES))],
    tags=["History"],
)
@app.get(
    f"{PREFIX}/{{rule_id}}/audit",
    dependencies=[Depends(require_roles(*RULE_READ_ROLES))],
    tags=["History"],
)
def history(rule_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    rule = find_rule(session, rule_id)
    rows = list(
        session.scalars(
            select(RuleAuditLog)
            .where(RuleAuditLog.rule_id == rule.id)
            .order_by(RuleAuditLog.timestamp, RuleAuditLog.id)
        )
    )
    data = [
        {
            "id": str(item.id),
            "ruleId": rule.rule_id,
            "ruleVersion": item.rule_version,
            "action": item.action,
            "userId": item.user_id,
            "timestamp": item.timestamp.isoformat(),
            "oldValue": item.old_value_json,
            "newValue": item.new_value_json,
            "reason": item.reason,
        }
        for item in rows
    ]
    return _page(data)


__all__ = ["app"]
