from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    Customer,
    LabelCatalogEntry,
    LabelCatalogVersion,
    MetricSnapshot,
    Rule,
    RuleAuditLog,
    RuleVersion,
)
from boa_oi.platform import (
    READ_ROLES,
    Principal,
    Problem,
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


class LabelUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=180)
    active: bool = True
    expectedVersion: int = Field(ge=1)
    justification: str = Field(min_length=8, max_length=1_000)

    @field_validator("label", "justification")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


def _serialize_label(entry: LabelCatalogEntry) -> dict[str, Any]:
    return {
        "namespace": entry.namespace,
        "code": entry.code,
        "locale": entry.locale,
        "label": entry.label,
        "active": entry.active,
        "version": entry.current_version,
        "updatedAt": entry.updated_at.isoformat(),
        "updatedBy": entry.updated_by,
        "justification": entry.justification,
    }


@app.get(
    "/internal/v1/labels",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Labels"],
)
def list_labels(
    request: Request,
    locale: str = "fr-FR",
    include_inactive: Annotated[bool, Query(alias="includeInactive")] = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"locale", "includeInactive"})
    stmt = select(LabelCatalogEntry).where(LabelCatalogEntry.locale == locale)
    if not include_inactive:
        stmt = stmt.where(LabelCatalogEntry.active.is_(True))
    entries = list(
        session.scalars(stmt.order_by(LabelCatalogEntry.namespace, LabelCatalogEntry.code))
    )
    return {
        "locale": locale,
        "labels": {entry.code: entry.label for entry in entries},
        "data": [_serialize_label(entry) for entry in entries],
    }


@app.get(
    "/internal/v1/labels/{namespace}/{code}/versions",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Labels"],
)
def label_versions(
    namespace: str,
    code: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    entry = session.scalar(
        select(LabelCatalogEntry).where(
            LabelCatalogEntry.namespace == namespace.upper(),
            LabelCatalogEntry.code == code.upper(),
            LabelCatalogEntry.locale == "fr-FR",
        )
    )
    if entry is None:
        raise not_found("Label")
    versions = list(
        session.scalars(
            select(LabelCatalogVersion)
            .where(LabelCatalogVersion.catalog_entry_id == entry.id)
            .order_by(LabelCatalogVersion.version.desc())
        )
    )
    return {
        "data": [
            {
                "version": item.version,
                "label": item.label,
                "active": item.active,
                "createdAt": item.created_at.isoformat(),
                "createdBy": item.created_by,
                "justification": item.justification,
            }
            for item in versions
        ],
        "meta": {"totalCount": len(versions)},
    }


@app.put("/internal/v1/labels/{namespace}/{code}", tags=["Labels"])
def update_label(
    namespace: str,
    code: str,
    payload: LabelUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    entry = session.scalar(
        select(LabelCatalogEntry)
        .where(
            LabelCatalogEntry.namespace == namespace.upper(),
            LabelCatalogEntry.code == code.upper(),
            LabelCatalogEntry.locale == "fr-FR",
        )
        .with_for_update()
    )
    if entry is None:
        raise not_found("Label")
    if entry.current_version != payload.expectedVersion:
        raise Problem(
            409,
            "LABEL_VERSION_CONFLICT",
            f"Label version {entry.current_version} is current; refresh before updating.",
        )
    if entry.label == payload.label and entry.active == payload.active:
        return _serialize_label(entry)
    actor = _principal(principal)
    entry.current_version += 1
    entry.label = payload.label
    entry.active = payload.active
    entry.updated_by = actor
    entry.justification = payload.justification
    session.add(
        LabelCatalogVersion(
            catalog_entry_id=entry.id,
            version=entry.current_version,
            label=payload.label,
            active=payload.active,
            created_by=actor,
            justification=payload.justification,
        )
    )
    session.flush()
    return _serialize_label(entry)


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
