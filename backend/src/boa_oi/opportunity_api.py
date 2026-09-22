from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, func, inspect, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from boa_oi.audit import DecisionAuditBuilder
from boa_oi.catalog import PRODUCTS_BY_CODE, family_status
from boa_oi.export_xlsx import (
    MAX_EXPORT_ROWS,
    XLSX_MIME,
    build_workbook,
    opportunity_columns,
)
from boa_oi.http_clients import service_request
from boa_oi.models.entities import (
    AuditLog,
    Customer,
    DecisionAudit,
    FlowVisibilityPolicy,
    Opportunity,
    OpportunityEvidence,
    OpportunityRule,
    PortfolioAssignment,
    RelationshipManager,
    ScoringPolicy,
)
from boa_oi.opportunities import OpportunityCandidate, OpportunityContext, OpportunityEngine
from boa_oi.opportunities.domain import ConditionEvidence
from boa_oi.platform import (
    ADMIN_ROLES,
    READ_ROLES,
    Principal,
    Problem,
    correlation_id,
    create_service_app,
    current_principal,
    decode_cursor,
    get_session,
    not_found,
    page_response,
    reject_unknown_filters,
    require_roles,
)
from boa_oi.resilience import FallbackMode, MLScoreResult, ResilientMLClient
from boa_oi.scoring_policy.routes import router as scoring_policy_router
from boa_oi.scoring_policy.service import active_policy
from boa_oi.technical.config import (
    OpportunityRuleConfig,
    RuleSetConfig,
    active_rule_set,
)
from boa_oi.technical.ids import deterministic_uuid
from boa_oi.visibility import VisibilityLevel

app = create_service_app(
    "opportunity-service",
    "Deterministic, versioned, explainable and audited SME opportunities.",
)
app.include_router(scoring_policy_router)
PREFIX = "/internal/v1"
ACTIVE_OPPORTUNITY_STATUSES = frozenset({"OPEN", "ACCEPTED", "CONTACTED"})
TERMINAL_OPPORTUNITY_STATUSES = frozenset({"CONVERTED", "DISMISSED", "DEFERRED", "EXPIRED"})
OPPORTUNITY_STATUSES = ACTIVE_OPPORTUNITY_STATUSES | TERMINAL_OPPORTUNITY_STATUSES
OPPORTUNITY_TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"ACCEPTED", "CONTACTED", "DISMISSED", "DEFERRED", "EXPIRED"}),
    "ACCEPTED": frozenset({"CONTACTED", "DISMISSED", "DEFERRED", "EXPIRED"}),
    "CONTACTED": frozenset({"CONVERTED", "DISMISSED", "DEFERRED", "EXPIRED"}),
    "CONVERTED": frozenset(),
    "DISMISSED": frozenset(),
    "DEFERRED": frozenset(),
    "EXPIRED": frozenset(),
}
DEFAULT_OPPORTUNITY_TTL_DAYS = int(os.getenv("OPPORTUNITY_TTL_DAYS", "90"))
DEFAULT_TERMINAL_COOLDOWN_DAYS = int(os.getenv("OPPORTUNITY_COOLDOWN_DAYS", "30"))
MINIMUM_HISTORY_DAYS = 90
ML_TIMEOUT_SECONDS = float(os.getenv("ML_TIMEOUT_SECONDS", "2.0"))
ML_MAX_RETRIES = int(os.getenv("ML_MAX_RETRIES", "1"))
ML_CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("ML_CIRCUIT_FAILURE_THRESHOLD", "3"))
ML_CIRCUIT_RECOVERY_SECONDS = float(os.getenv("ML_CIRCUIT_RECOVERY_SECONDS", "30"))
ML_MAX_SCORE_AGE_SECONDS = float(os.getenv("ML_MAX_SCORE_AGE_SECONDS", "300"))
HORIZON_LABELS = {
    "0-1_MONTH": "Contacter dans le mois.",
    "0-3_MONTHS": "Contacter dans les 3 mois.",
    "1-3_MONTHS": "Contacter dans les 1 à 3 mois.",
    "3-6_MONTHS": "Contacter dans les 3 à 6 mois.",
}


class GenerationRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    asOf: date
    engineVersion: str | None = None
    ruleVersion: str | None = None


class OpportunityTransitionRequest(BaseModel):
    status: Literal[
        "OPEN", "ACCEPTED", "CONTACTED", "CONVERTED", "DISMISSED", "DEFERRED", "EXPIRED"
    ]
    reason: str = Field(min_length=3, max_length=1_000)
    occurredAt: datetime | None = None
    cooldownUntil: datetime | None = None
    actorSubjectId: str | None = Field(default=None, min_length=1, max_length=120)


class ExpirationRequest(BaseModel):
    asOf: datetime | None = None
    reason: str = Field(
        default="Opportunity validity period elapsed", min_length=3, max_length=1_000
    )


def url_for(name: str) -> str:
    value = os.getenv(f"{name.upper()}_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{name.upper()}_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


async def _ml_transport(payload: dict[str, Any]) -> dict[str, Any]:
    return await service_request(
        "POST",
        f"{url_for('ml_engine')}/internal/v1/ml/customers/{payload['customerId']}/score",
        correlation_id=str(payload["correlationId"]),
        json={"asOf": payload["asOf"]},
        incoming_authorization=payload.get("authorization"),
        timeout=ML_TIMEOUT_SECONDS,
    )


_ml_client = ResilientMLClient(
    _ml_transport,
    timeout=ML_TIMEOUT_SECONDS,
    max_retries=ML_MAX_RETRIES,
    failure_threshold=ML_CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=ML_CIRCUIT_RECOVERY_SECONDS,
    max_score_age=ML_MAX_SCORE_AGE_SECONDS,
    default_mode=FallbackMode.POC_SHADOW,
)


def persist_ml_audit(
    session: Session,
    *,
    customer_id: str,
    result: MLScoreResult,
    request: Request,
) -> None:
    trace_id = correlation_id(request)
    event = result.audit_event.as_dict()
    session.execute(
        pg_insert(AuditLog)
        .values(
            id=deterministic_uuid("ml-resilience-audit", trace_id, customer_id, result.mode.value),
            actor_subject_id="opportunity-service",
            service_name="opportunity-service",
            action=(
                "ML_SHADOW_SCORE_OBSERVED"
                if result.mode is FallbackMode.POC_SHADOW
                else "ML_SCORE_ACCEPTED"
                if result.mode is FallbackMode.HYBRID_ML
                else "ML_FALLBACK_APPLIED"
            ),
            resource_type="OPPORTUNITY_GENERATION",
            resource_id=customer_id,
            correlation_id=trace_id,
            result=result.mode.value,
            metadata_json=event,
        )
        .on_conflict_do_nothing(index_elements=[AuditLog.id])
    )


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
        "recommendationNature": item.recommendation_nature,
        "evidenceCount": len(item.explanation_json.get("evidence", [])),
        "generatedAt": item.generated_at.isoformat(),
        "engineVersion": item.engine_version,
        "ruleVersion": item.rule_version,
        "scoringPolicyId": item.scoring_policy_id,
        "scoringPolicyVersion": item.scoring_policy_version,
        "fallbackMode": item.fallback_mode,
        "statusUpdatedAt": item.status_updated_at.isoformat(),
        "statusReason": item.status_reason,
        "expiresAt": item.expires_at.isoformat() if item.expires_at else None,
        "cooldownUntil": item.cooldown_until.isoformat() if item.cooldown_until else None,
        "lastActionAt": item.last_action_at.isoformat() if item.last_action_at else None,
    }


def scoped_customer_ids(session: Session, principal: Principal) -> Any | None:
    if {"ADMIN", "SERVICE"} & principal.roles:
        return None
    manager = aliased(RelationshipManager)
    bind = session.get_bind()
    assignments_available = bind.dialect.name != "sqlite" or inspect(bind).has_table(
        PortfolioAssignment.__tablename__, schema="customer"
    )
    if assignments_available:
        assignment = aliased(PortfolioAssignment)
        stmt = (
            select(assignment.customer_id)
            .join(manager, assignment.relationship_manager_id == manager.id)
            .where(
                assignment.valid_from <= datetime.now(timezone.utc),
                or_(
                    assignment.valid_to.is_(None),
                    assignment.valid_to > datetime.now(timezone.utc),
                ),
            )
        )
        branch_code: Any = assignment.branch_code
    else:
        stmt = select(Customer.id).join(manager, Customer.rm_id == manager.id)
        branch_code = manager.branch_code
    if "RELATIONSHIP_MANAGER" in principal.roles:
        if not principal.relationship_manager_ids:
            raise Problem(
                403,
                "PORTFOLIO_SCOPE_MISSING",
                "No relationship-manager scope is assigned.",
            )
        return stmt.where(manager.subject_id.in_(principal.relationship_manager_ids))
    if "BRANCH_MANAGER" in principal.roles:
        if not principal.branch_ids:
            raise Problem(403, "PORTFOLIO_SCOPE_MISSING", "No branch scope is assigned.")
        return stmt.where(branch_code.in_(principal.branch_ids))
    raise Problem(403, "PORTFOLIO_SCOPE_FORBIDDEN", "No commercial portfolio scope is assigned.")


def find(item_id: str, session: Session, principal: Principal | None = None) -> Opportunity:
    stmt = select(Opportunity).where(Opportunity.opportunity_ref == item_id)
    if principal is not None:
        customer_scope = scoped_customer_ids(session, principal)
        if customer_scope is not None:
            stmt = stmt.where(Opportunity.customer_id.in_(customer_scope))
    item = session.scalar(stmt)
    if item is None:
        raise not_found("Opportunity")
    return item


def find_for_update(item_id: str, session: Session) -> Opportunity:
    item = session.scalar(
        select(Opportunity).where(Opportunity.opportunity_ref == item_id).with_for_update()
    )
    if item is None:
        raise not_found("Opportunity")
    return item


def lifecycle_policy(raw: dict[str, Any] | None) -> dict[str, int]:
    source = (raw or {}).get("lifecycle", raw or {})
    aliases = {
        "validity_days": ("validity_days", "validityDays"),
        "dismissed_cooldown_days": (
            "dismissed_cooldown_days",
            "dismissedCooldownDays",
        ),
        "converted_cooldown_days": (
            "converted_cooldown_days",
            "convertedCooldownDays",
        ),
        "deferred_cooldown_days": (
            "deferred_cooldown_days",
            "deferredCooldownDays",
        ),
        "expired_cooldown_days": ("expired_cooldown_days", "expiredCooldownDays"),
    }
    defaults = {
        "validity_days": DEFAULT_OPPORTUNITY_TTL_DAYS,
        "dismissed_cooldown_days": DEFAULT_TERMINAL_COOLDOWN_DAYS,
        "converted_cooldown_days": 180,
        "deferred_cooldown_days": DEFAULT_TERMINAL_COOLDOWN_DAYS,
        "expired_cooldown_days": 7,
    }
    for target, keys in aliases.items():
        for key in keys:
            if key in source:
                defaults[target] = int(source[key])
                break
    return defaults


def policy_for_opportunity(session: Session, item: Opportunity) -> dict[str, int]:
    rule = session.get(OpportunityRule, item.rule_id)
    return lifecycle_policy(rule.configuration_json if rule is not None else None)


def cooldown_days_for(status: str, policy: dict[str, int]) -> int:
    return {
        "DISMISSED": policy["dismissed_cooldown_days"],
        "CONVERTED": policy["converted_cooldown_days"],
        "DEFERRED": policy["deferred_cooldown_days"],
        "EXPIRED": policy["expired_cooldown_days"],
    }.get(status, DEFAULT_TERMINAL_COOLDOWN_DAYS)


def serialize_lifecycle_policy(raw: dict[str, Any] | None) -> dict[str, int]:
    policy = lifecycle_policy(raw)
    return {
        "validityDays": policy["validity_days"],
        "dismissedCooldownDays": policy["dismissed_cooldown_days"],
        "convertedCooldownDays": policy["converted_cooldown_days"],
        "deferredCooldownDays": policy["deferred_cooldown_days"],
        "expiredCooldownDays": policy["expired_cooldown_days"],
    }


def audit_opportunity_transition(
    session: Session,
    *,
    item: Opportunity,
    actor_subject_id: str,
    event: str,
    correlation: str,
    before: dict[str, Any],
    after: dict[str, Any],
    command_id: str | None = None,
    command_hash: str | None = None,
    authorized_by: str | None = None,
) -> None:
    occurred_at = datetime.now(timezone.utc)
    session.add(
        AuditLog(
            id=(
                deterministic_uuid(
                    "opportunity-transition-command",
                    item.opportunity_ref,
                    command_id,
                )
                if command_id is not None
                else deterministic_uuid(
                    "opportunity-lifecycle-audit",
                    item.opportunity_ref,
                    event,
                    correlation,
                    occurred_at.isoformat(),
                )
            ),
            occurred_at=occurred_at,
            actor_subject_id=actor_subject_id,
            service_name="opportunity-service",
            action=event,
            resource_type="OPPORTUNITY",
            resource_id=item.opportunity_ref,
            correlation_id=correlation,
            result="SUCCESS",
            metadata_json={
                "before": before,
                "after": after,
                "commandId": command_id,
                "commandHash": command_hash,
                "authorizedBy": authorized_by,
            },
        )
    )


def lifecycle_time(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            "Lifecycle timestamps must include a timezone.",
        )
    return result.astimezone(timezone.utc)


def transition_opportunity(
    item: Opportunity,
    target_status: str,
    *,
    reason: str,
    occurred_at: datetime,
    cooldown_until: datetime | None = None,
    cooldown_days: int = DEFAULT_TERMINAL_COOLDOWN_DAYS,
) -> Opportunity:
    if item.status == target_status:
        if item.status in ACTIVE_OPPORTUNITY_STATUSES:
            if cooldown_until is not None:
                raise Problem(
                    422,
                    "VALIDATION_ERROR",
                    "cooldownUntil is only accepted for a terminal status.",
                )
            item.status_updated_at = occurred_at
            item.status_reason = reason
            item.last_action_at = occurred_at
            return item
        persisted_cooldown = item.cooldown_until
        if persisted_cooldown is not None and persisted_cooldown.tzinfo is None:
            persisted_cooldown = persisted_cooldown.replace(tzinfo=timezone.utc)
        if (
            cooldown_until is not None
            and persisted_cooldown is not None
            and (lifecycle_time(cooldown_until) != persisted_cooldown.astimezone(timezone.utc))
        ):
            raise Problem(
                409,
                "OPPORTUNITY_TRANSITION_REPLAY_CONFLICT",
                "The terminal transition was already recorded with another cooldown.",
            )
        return item
    allowed = OPPORTUNITY_TRANSITIONS.get(item.status)
    if allowed is None or target_status not in allowed:
        raise Problem(
            409,
            "INVALID_OPPORTUNITY_TRANSITION",
            f"Opportunity cannot transition from {item.status} to {target_status}.",
            details=[
                {
                    "field": "status",
                    "code": "INVALID_OPPORTUNITY_TRANSITION",
                    "message": f"Allowed targets: {', '.join(sorted(allowed or ())) or 'none'}.",
                }
            ],
        )
    if target_status in TERMINAL_OPPORTUNITY_STATUSES:
        terminal_cooldown = cooldown_until or occurred_at + timedelta(days=cooldown_days)
        terminal_cooldown = lifecycle_time(terminal_cooldown)
        if terminal_cooldown < occurred_at:
            raise Problem(
                422,
                "VALIDATION_ERROR",
                "cooldownUntil cannot be before occurredAt.",
            )
        item.cooldown_until = terminal_cooldown
    elif cooldown_until is not None:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            "cooldownUntil is only accepted for a terminal status.",
        )
    item.status = target_status
    item.status_updated_at = occurred_at
    item.status_reason = reason
    item.last_action_at = occurred_at
    return item


def expire_due_opportunities(
    session: Session,
    *,
    as_of: datetime,
    reason: str = "Opportunity validity period elapsed",
    customer_refs: list[str] | None = None,
    actor_subject_id: str | None = None,
    audit_correlation: str | None = None,
) -> int:
    stmt = select(Opportunity).where(
        Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
        Opportunity.expires_at.is_not(None),
        Opportunity.expires_at <= as_of,
    )
    if customer_refs is not None:
        stmt = stmt.where(Opportunity.customer_ref.in_(customer_refs))
    rows = list(session.scalars(stmt.with_for_update(skip_locked=True)))
    for item in rows:
        before = serialize(item)
        previous_last_action_at = item.last_action_at
        policy = policy_for_opportunity(session, item)
        transition_opportunity(
            item,
            "EXPIRED",
            reason=reason,
            occurred_at=as_of,
            cooldown_days=cooldown_days_for("EXPIRED", policy),
        )
        item.last_action_at = previous_last_action_at
        if actor_subject_id is not None and audit_correlation is not None:
            audit_opportunity_transition(
                session,
                item=item,
                actor_subject_id=actor_subject_id,
                event="OPPORTUNITY_EXPIRED",
                correlation=audit_correlation,
                before=before,
                after=serialize(item),
            )
    return len(rows)


def suppress_low_visibility_cash_opportunities(
    session: Session,
    *,
    customer_ref: str,
    visibility_level: VisibilityLevel,
    as_of: datetime,
    actor_subject_id: str,
    audit_correlation: str,
) -> int:
    if visibility_level != "LOW":
        return 0
    rows = list(
        session.scalars(
            select(Opportunity)
            .where(
                Opportunity.customer_ref == customer_ref,
                Opportunity.opportunity_type == "CASH_INVESTMENT",
                Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
            )
            .with_for_update(skip_locked=True)
        )
    )
    for item in rows:
        before = serialize(item)
        previous_last_action_at = item.last_action_at
        policy = policy_for_opportunity(session, item)
        transition_opportunity(
            item,
            "EXPIRED",
            reason="Placement retiré : visibilité des flux faible",
            occurred_at=as_of,
            cooldown_days=cooldown_days_for("EXPIRED", policy),
        )
        item.last_action_at = previous_last_action_at
        audit_opportunity_transition(
            session,
            item=item,
            actor_subject_id=actor_subject_id,
            event="OPPORTUNITY_EXPIRED_LOW_VISIBILITY",
            correlation=audit_correlation,
            before=before,
            after=serialize(item),
        )
    return len(rows)


def claim_generation_customers(session: Session, customer_ids: list[str]) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    for customer_id in sorted(set(customer_ids)):
        claimed = session.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    func.hashtext(customer_id),
                    func.hashtext("OPPORTUNITY_GENERATION"),
                )
            )
        )
        if not claimed:
            raise Problem(
                409,
                "GENERATION_IN_PROGRESS",
                f"Another generation is already evaluating customer {customer_id}.",
            )


def classify_generation(
    session: Session,
    *,
    customer_id: Any,
    opportunity_type: str,
    as_of: datetime,
) -> tuple[Literal["CREATED", "REFRESHED", "SUPPRESSED"], Opportunity | None, Opportunity | None]:
    if session.get_bind().dialect.name == "postgresql":
        claimed = session.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    func.hashtext(str(customer_id)),
                    func.hashtext(opportunity_type),
                )
            )
        )
        if not claimed:
            raise Problem(
                409,
                "GENERATION_IN_PROGRESS",
                "Another generation is already evaluating this customer and opportunity type.",
            )
    terminal = session.scalar(
        select(Opportunity)
        .where(
            Opportunity.customer_id == customer_id,
            Opportunity.opportunity_type == opportunity_type,
            Opportunity.status.in_(TERMINAL_OPPORTUNITY_STATUSES),
            Opportunity.cooldown_until.is_not(None),
            Opportunity.cooldown_until > as_of,
        )
        .order_by(Opportunity.cooldown_until.desc())
        .with_for_update()
    )
    active = session.scalar(
        select(Opportunity)
        .where(
            Opportunity.customer_id == customer_id,
            Opportunity.opportunity_type == opportunity_type,
            Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
        )
        .order_by(Opportunity.generated_at.desc())
        .with_for_update()
    )
    decision: Literal["CREATED", "REFRESHED", "SUPPRESSED"] = (
        "SUPPRESSED" if terminal is not None else "REFRESHED" if active else "CREATED"
    )
    return decision, terminal, active


def parse_opportunity_date_filter(request: Request, name: str) -> date | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            f"{name} must be a valid ISO date (YYYY-MM-DD).",
            details=[{"field": name, "code": "date", "message": f"Invalid date: {raw}"}],
        ) from exc
    if parsed.isoformat() != raw:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            f"{name} must use the YYYY-MM-DD format.",
        )
    return parsed


def parse_confidence_filter(request: Request, name: str) -> Decimal | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            f"{name} must be a decimal between 0 and 1.",
            details=[
                {
                    "field": name,
                    "code": "decimal_parsing",
                    "message": f"Invalid value: {raw}",
                }
            ],
        ) from exc
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            f"{name} must be a decimal between 0 and 1.",
        )
    return parsed


def list_for(
    request: Request,
    session: Session,
    principal: Principal,
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
    min_confidence = parse_confidence_filter(request, "minConfidence")
    max_confidence = parse_confidence_filter(request, "maxConfidence")
    from_date = parse_opportunity_date_filter(request, "fromDate")
    to_date = parse_opportunity_date_filter(request, "toDate")
    if (
        min_confidence is not None
        and max_confidence is not None
        and min_confidence > max_confidence
    ):
        raise Problem(422, "VALIDATION_ERROR", "maxConfidence must be at least minConfidence.")
    if from_date is not None and to_date is not None and to_date <= from_date:
        raise Problem(422, "VALIDATION_ERROR", "toDate must be after fromDate.")
    offset = decode_cursor(cursor)
    stmt = select(Opportunity)
    customer_scope = scoped_customer_ids(session, principal)
    if customer_scope is not None:
        stmt = stmt.where(Opportunity.customer_id.in_(customer_scope))
    sector = params.get("sector")
    customer_segment = params.get("customerSegment")
    relationship_manager_id = params.get("relationshipManagerId")
    if sector or customer_segment or relationship_manager_id:
        stmt = stmt.join(Customer, Opportunity.customer_id == Customer.id)
    if sector:
        stmt = stmt.where(Customer.sector_code == sector)
    if customer_segment:
        if customer_segment.upper() == "SME":
            stmt = stmt.where(Customer.segment_code.in_(("SMALL", "MEDIUM")))
        else:
            stmt = stmt.where(Customer.segment_code == customer_segment)
    if relationship_manager_id:
        stmt = (
            stmt.join(
                PortfolioAssignment,
                and_(
                    PortfolioAssignment.customer_id == Customer.id,
                    PortfolioAssignment.valid_from <= datetime.now(timezone.utc),
                    or_(
                        PortfolioAssignment.valid_to.is_(None),
                        PortfolioAssignment.valid_to > datetime.now(timezone.utc),
                    ),
                ),
            )
            .join(
                RelationshipManager,
                PortfolioAssignment.relationship_manager_id == RelationshipManager.id,
            )
            .where(RelationshipManager.subject_id == relationship_manager_id)
        )
    target = customer_id or params.get("customerId")
    if target:
        stmt = stmt.where(Opportunity.customer_ref == target)
    opp_type = params.get("type") or params.get("opportunityType")
    if opp_type:
        stmt = stmt.where(Opportunity.opportunity_type == opp_type)
    if min_confidence is not None:
        stmt = stmt.where(Opportunity.confidence_score >= min_confidence)
    if max_confidence is not None:
        stmt = stmt.where(Opportunity.confidence_score <= max_confidence)
    if params.get("priorityLevel"):
        stmt = stmt.where(Opportunity.priority_level == params["priorityLevel"])
    if params.get("horizon"):
        stmt = stmt.where(Opportunity.horizon == params["horizon"])
    if params.get("status"):
        stmt = stmt.where(Opportunity.status == params["status"])
    if from_date is not None:
        stmt = stmt.where(
            Opportunity.generated_at >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        )
    if to_date is not None:
        stmt = stmt.where(
            Opportunity.generated_at < datetime.combine(to_date, time.min, tzinfo=timezone.utc)
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
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(request, session, principal, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/exports/opportunities.xlsx",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Exports"],
)
def export_opportunities(
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> Response:
    reject_unknown_filters(
        request,
        {
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
    result = list_for(
        request,
        session,
        principal,
        page_size=MAX_EXPORT_ROWS,
        cursor=None,
    )
    if result["meta"]["hasMore"]:
        raise Problem(
            413,
            "EXPORT_LIMIT_EXCEEDED",
            f"The pilot export is limited to {MAX_EXPORT_ROWS} rows.",
        )
    trace_id = correlation_id(request)
    export_id = str(uuid4())
    artifact = build_workbook(
        filename=f"opportunites-{datetime.now(timezone.utc).date().isoformat()}.xlsx",
        sheet_name="Opportunités",
        columns=opportunity_columns(),
        rows=result["data"],
        metadata={
            "exportId": export_id,
            "exportType": "OPPORTUNITIES",
            "actorSubjectId": principal.subject,
            "scope": {
                "relationshipManagerIds": principal.relationship_manager_ids,
                "branchIds": principal.branch_ids,
            },
            "filters": dict(request.query_params),
            "correlationId": trace_id,
        },
    )
    session.add(
        AuditLog(
            id=uuid4(),
            actor_subject_id=principal.subject,
            service_name="opportunity-service",
            action="EXPORT_XLSX_SUCCEEDED",
            resource_type="OPPORTUNITY_EXPORT",
            resource_id=export_id,
            correlation_id=trace_id,
            result="SUCCESS",
            metadata_json={
                "rowCount": artifact.row_count,
                "sha256": artifact.sha256,
                "filters": dict(request.query_params),
            },
        )
    )
    return Response(
        artifact.content,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Cache-Control": "no-store",
            "X-Content-SHA256": artifact.sha256,
            "X-Correlation-ID": trace_id,
        },
    )


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
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(
        request,
        session,
        principal,
        customer_id=customer_id,
        page_size=page_size,
        cursor=cursor,
    )


@app.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Opportunities"],
)
def get_opportunity(
    opportunity_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return serialize(find(opportunity_id, session, principal))


@app.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/explanation",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Opportunities"],
)
def get_explanation(
    opportunity_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return find(opportunity_id, session, principal).explanation_json


@app.post(
    f"{PREFIX}/opportunities/{{opportunity_id}}/transition",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Opportunities"],
)
def transition(
    opportunity_id: str,
    payload: OpportunityTransitionRequest,
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ] = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    occurred_at = lifecycle_time(payload.occurredAt)
    item = find_for_update(opportunity_id, session)
    command_audit_id = (
        deterministic_uuid(
            "opportunity-transition-command",
            opportunity_id,
            idempotency_key,
        )
        if idempotency_key is not None
        else None
    )
    command_hash = hashlib.sha256(
        json.dumps(
            payload.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if command_audit_id is not None:
        existing_command = session.get(AuditLog, command_audit_id)
        if existing_command is not None:
            if existing_command.metadata_json.get("commandHash") != command_hash:
                raise Problem(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was reused with different transition content.",
                )
            return serialize(item)
    before = serialize(item)
    policy = policy_for_opportunity(session, item)
    item = transition_opportunity(
        item,
        payload.status,
        reason=payload.reason,
        occurred_at=occurred_at,
        cooldown_until=payload.cooldownUntil,
        cooldown_days=cooldown_days_for(payload.status, policy),
    )
    after = serialize(item)
    actor_subject_id = (
        payload.actorSubjectId
        if payload.actorSubjectId is not None and "SERVICE" in principal.roles
        else principal.subject
    )
    audit_opportunity_transition(
        session,
        item=item,
        actor_subject_id=actor_subject_id,
        event=f"OPPORTUNITY_{payload.status}",
        correlation=correlation_id(request),
        before=before,
        after=after,
        command_id=idempotency_key,
        command_hash=command_hash,
        authorized_by=principal.subject,
    )
    return after


@app.post(
    f"{PREFIX}/opportunities/maintenance/expire",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Operations"],
)
def expire(
    payload: ExpirationRequest,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    as_of = lifecycle_time(payload.asOf)
    expired = expire_due_opportunities(
        session,
        as_of=as_of,
        reason=payload.reason,
        actor_subject_id=principal.subject,
        audit_correlation=correlation_id(request),
    )
    return {"status": "COMPLETED", "expired": expired, "asOf": as_of.isoformat()}


def configured_rules(session: Session) -> RuleSetConfig:
    config = active_rule_set()
    rows = [
        row
        for row in session.scalars(
            select(OpportunityRule)
            .where(OpportunityRule.active.is_(True))
            .order_by(OpportunityRule.created_at, OpportunityRule.version)
        )
        if row.configuration_json.get("source") != "rule-studio"
    ]
    updates = {
        row.opportunity_type: OpportunityRuleConfig.model_validate(row.configuration_json)
        for row in rows
    }
    raw = config.model_dump(mode="python")
    raw["opportunity_rules"].update(
        {key: value.model_dump(mode="python") for key, value in updates.items()}
    )
    bind = session.get_bind()
    policy = (
        session.scalar(
            select(FlowVisibilityPolicy)
            .where(FlowVisibilityPolicy.active.is_(True))
            .order_by(FlowVisibilityPolicy.version.desc())
            .limit(1)
        )
        if bind.dialect.name != "sqlite"
        or inspect(bind).has_table(FlowVisibilityPolicy.__tablename__, schema="analytics")
        else None
    )
    if policy is not None and "FLOW_DOMICILIATION" in raw["opportunity_rules"]:
        raw["opportunity_rules"]["FLOW_DOMICILIATION"]["visibility_policy"] = dict(
            policy.configuration_json
        )
    return RuleSetConfig.model_validate(raw)


def rule_engine_metrics(
    rows: list[dict[str, Any]],
    *,
    flow_visibility: dict[str, Any] | None = None,
    banking_relationship: str | None = None,
    declared_turnover_growth_rate: float = 0.0,
    no_recent_domiciliation_action: bool = True,
) -> dict[str, Any]:
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
    visibility = flow_visibility or {}
    level = str(visibility.get("level") or "UNKNOWN")
    fingerprint_growth = int(visibility.get("fingerprintGrowth90d") or 0)
    visibility_opportunity = level in {"PARTIAL", "LOW"} or banking_relationship in {
        "PRIMARY",
        "SECONDARY",
    }
    visibility_facts: dict[str, Any] = {
        "FLOW_VISIBILITY_OPPORTUNITY": visibility_opportunity,
        "FLOW_VISIBILITY_LEVEL": level,
        "FLOW_VISIBILITY_SHARE": visibility.get("estimatedShare"),
        "FINGERPRINT_GROWTH_90D": fingerprint_growth,
        "DECLARED_TURNOVER_GROWTH": declared_turnover_growth_rate,
        "NO_RECENT_DOMICILIATION_ACTION": no_recent_domiciliation_action,
    }
    result.update(visibility_facts)
    for code, value in visibility_facts.items():
        result[f"{code}:90D"] = value
    result["NO_RECENT_DOMICILIATION_ACTION:180D"] = no_recent_domiciliation_action
    result["DECLARED_TURNOVER_GROWTH:365D"] = declared_turnover_growth_rate
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
    operator = _STUDIO_OPERATORS.get(str(item.get("operator") or ""), "configured")
    actual = item.get("actual")
    threshold = item.get("threshold")
    if actual is None or threshold is None or isinstance(actual, (list, dict)):
        return f"{item['metric']}: condition de règle publiée satisfaite"
    return f"{item['metric']}: observé={actual}, condition={operator} {threshold}"


def rule_engine_candidates(
    customer_id: str,
    as_of: date,
    response: dict[str, Any],
    *,
    flow_visibility_level: Literal["HIGH", "PARTIAL", "LOW", "UNKNOWN"] = "UNKNOWN",
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
        product_codes = tuple(match.get("productCodes") or [])
        unknown_products = sorted(set(product_codes) - PRODUCTS_BY_CODE.keys())
        if unknown_products:
            raise Problem(
                409,
                "UNKNOWN_RULE_PRODUCT_CODES",
                f"Published rule {rule_id}:v{rule_version} references unknown catalogue codes.",
                details=[
                    {"field": "recommendation.products", "code": code} for code in unknown_products
                ],
            )
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
                what=str(
                    match.get("what")
                    or (
                        f"Règle publiée « {match.get('ruleName') or rule_id} » (version "
                        f"{rule_version}) : opportunité à qualifier avec le client."
                    )
                ),
                when=str(
                    match.get("whenText")
                    or HORIZON_LABELS.get(
                        str(match.get("horizon") or "1-3_MONTHS"),
                        str(match.get("horizon") or "1-3_MONTHS"),
                    )
                ),
                recommended_products=product_codes,
                recommendation_nature=(
                    "WIN_BACK" if flow_visibility_level in {"PARTIAL", "LOW"} else "NEED_DISCOVERY"
                ),
                evidence=evidence,
                as_of_date=as_of,
                generated_at=datetime.now(timezone.utc).isoformat(),
                engine_version=str(match.get("engineVersion") or "rule-engine"),
                rule_version=f"{rule_id}:v{rule_version}",
                rule_set_version="rule-studio",
                lifecycle_policy=lifecycle_policy(match.get("lifecycle")),
            )
        )
    return candidates


def rerank_with_propensity(
    candidate: OpportunityCandidate,
    propensity: dict[str, Any],
    *,
    rules_weight: float,
    ml_weight: float,
) -> OpportunityCandidate:
    if propensity.get("deploymentMode") != "POC_SHADOW" or rules_weight != 1.0 or ml_weight != 0.0:
        raise Problem(
            409,
            "ML_SHADOW_POLICY_REQUIRED",
            "Pilot prioritization requires POC_SHADOW with rulesWeight=1 and mlWeight=0.",
        )
    return rules_only_candidate(candidate)


def rules_only_candidate(candidate: OpportunityCandidate) -> OpportunityCandidate:
    rules_score = float(candidate.priority_score)
    normalized = rules_score / 100 if rules_score > 1 else rules_score
    priority_level: Literal["P1", "P2", "P3", "P4"] = (
        "P1"
        if normalized >= 0.8
        else "P2"
        if normalized >= 0.6
        else "P3"
        if normalized >= 0.4
        else "P4"
    )
    return candidate.model_copy(
        update={
            "priority_score": round(normalized * 100, 4),
            "priority_level": priority_level,
            "priority_components": (
                *candidate.priority_components,
                {
                    "name": "ml_fallback_rules_only",
                    "weighted_value": 0.0,
                    "weight": 0.0,
                },
            ),
            "why": (*candidate.why, "Priorité calculée en mode RULES_ONLY explicite."),
            "engine_version": f"{candidate.engine_version}+rules-only",
        }
    )


def hydrate_recommended_products(
    product_codes: tuple[str, ...], catalog: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    unavailable = sorted(set(product_codes) - catalog.keys())
    if unavailable:
        raise Problem(
            409,
            "UNAVAILABLE_RULE_PRODUCT_CODES",
            "A matching rule references products absent or inactive in Product Service: "
            + ", ".join(unavailable),
        )
    return [catalog[code] for code in product_codes]


async def context_for(
    customer_id: str,
    as_of: date,
    request: Request,
    *,
    domiciliation_cooldown_days: int,
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
        params={"asOf": as_of.isoformat()},
        incoming_authorization=auth,
    )
    metrics_page = await service_request(
        "GET",
        f"{url_for('analytics')}/internal/v1/customers/{customer_id}/metrics",
        correlation_id=corr,
        params={
            "fromDate": as_of.isoformat(),
            "toDate": (as_of + timedelta(days=1)).isoformat(),
            "pageSize": 1000,
        },
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
    visibility = customer.get("flowVisibility") or {}
    raw_visibility_level = str(visibility.get("level") or "UNKNOWN")
    visibility_level = (
        cast(VisibilityLevel, raw_visibility_level)
        if raw_visibility_level in {"HIGH", "PARTIAL", "LOW", "UNKNOWN"}
        else "UNKNOWN"
    )
    recent_domiciliation_actions = await service_request(
        "GET",
        f"{url_for('action')}/internal/v1/customers/{customer_id}/actions",
        correlation_id=corr,
        params={
            "fromDate": (as_of - timedelta(days=domiciliation_cooldown_days - 1)).isoformat(),
            "toDate": (as_of + timedelta(days=1)).isoformat(),
            "pageSize": 1000,
        },
        incoming_authorization=auth,
    )
    has_recent_domiciliation = any(
        item.get("opportunityType") == "FLOW_DOMICILIATION"
        for item in recent_domiciliation_actions.get("data", [])
    )
    facts: dict[str, float | int | bool | str] = {
        "inflow_growth_rate": value("inflow_amount", "growthRate"),
        "inflow_growth_rate_seasonality_adjusted": adjusted("inflow_amount"),
        "supplier_payment_growth_rate": value("supplier_payment_amount", "growthRate"),
        "supplier_payment_growth_rate_seasonality_adjusted": adjusted("supplier_payment_amount"),
        "transaction_volume_growth_rate": value("transaction_count", "growthRate"),
        "transaction_volume_growth_rate_seasonality_adjusted": adjusted("transaction_count"),
        "no_recent_investment_financing": product_status.get("INVESTMENT_FINANCING")
        in {None, "ABSENT", "ABSENT_OR_ELSEWHERE"},
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
        in {None, "ABSENT", "ABSENT_OR_ELSEWHERE", "UNDERUTILIZED"},
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
        "flow_visibility_opportunity": visibility_level in {"PARTIAL", "LOW"}
        or customer.get("bankingRelationship") in {"PRIMARY", "SECONDARY"},
        "fingerprint_growth_90d": int(visibility.get("fingerprintGrowth90d") or 0),
        "declared_turnover_growth_rate": float(customer.get("declaredTurnoverGrowthRate") or 0),
        "no_recent_domiciliation_action": not has_recent_domiciliation,
    }
    history_complete = bool(metrics_90) and all(
        row.get("historyDays") is not None and row.get("observedFrom") is not None
        for row in metrics_90.values()
    )
    history_values = [int(row["historyDays"]) for row in metrics_90.values() if history_complete]
    history_days = min(history_values) if history_values else 0
    observed_from = min(
        (
            date.fromisoformat(str(row["observedFrom"]))
            for row in metrics_90.values()
            if row.get("observedFrom") is not None
        ),
        default=None,
    )
    if not history_complete or history_days < MINIMUM_HISTORY_DAYS or observed_from is None:
        raise Problem(
            422,
            "INSUFFICIENT_TRANSACTION_HISTORY",
            f"Customer {customer_id} has less than "
            f"{MINIMUM_HISTORY_DAYS} calendar days of transaction history.",
            details=[
                {
                    "field": "historyDays",
                    "code": "INSUFFICIENT_TRANSACTION_HISTORY",
                    "message": (
                        f"Observed {history_days} days from "
                        f"{observed_from.isoformat() if observed_from else 'unknown'}; "
                        f"{MINIMUM_HISTORY_DAYS} required. Recompute legacy snapshots first."
                    ),
                }
            ],
        )
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
        flow_visibility_level=visibility_level,
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
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    config = configured_rules(session)
    engine = OpportunityEngine(config)
    flow_rule = config.opportunity_rules.get("FLOW_DOMICILIATION")
    domiciliation_cooldown_days = int(
        (flow_rule.visibility_policy if flow_rule else {}).get("domiciliationCooldownDays", 180)
    )
    policy_version = active_policy(session)
    if policy_version is None:
        raise Problem(
            503,
            "ACTIVE_SCORING_POLICY_UNAVAILABLE",
            "No effective ACTIVE scoring policy is available.",
        )
    policy = session.get(ScoringPolicy, policy_version.policy_id)
    if policy is None:
        raise Problem(503, "SCORING_POLICY_NOT_FOUND", "Active scoring policy is invalid.")
    rules_weight = float(policy_version.rules_weight)
    ml_weight = float(policy_version.ml_weight)
    created = 0
    refreshed = 0
    suppressed = 0
    generation_time = datetime.combine(payload.asOf, time.min, tzinfo=timezone.utc)
    claim_generation_customers(session, payload.customerIds)
    expired = expire_due_opportunities(
        session,
        as_of=generation_time,
        customer_refs=payload.customerIds,
        actor_subject_id=principal.subject,
        audit_correlation=correlation_id(request),
    )
    shadow_customers = 0
    rules_only_customers = 0
    audit_builder = DecisionAuditBuilder()
    for customer_id in payload.customerIds:
        context, metrics, signals, catalog, customer = await context_for(
            customer_id,
            payload.asOf,
            request,
            domiciliation_cooldown_days=domiciliation_cooldown_days,
        )
        suppressed += suppress_low_visibility_cash_opportunities(
            session,
            customer_ref=customer_id,
            visibility_level=context.flow_visibility_level,
            as_of=generation_time,
            actor_subject_id=principal.subject,
            audit_correlation=correlation_id(request),
        )
        ml_result = await _ml_client.score(
            {
                "customerId": customer_id,
                "asOf": payload.asOf.isoformat(),
                "correlationId": correlation_id(request),
                "authorization": request.headers.get("Authorization"),
            },
            mode=FallbackMode.POC_SHADOW,
            as_of=payload.asOf,
        )
        persist_ml_audit(session, customer_id=customer_id, result=ml_result, request=request)
        shadow_propensity = dict(ml_result.response) if ml_result.response is not None else None
        if ml_result.mode is FallbackMode.POC_SHADOW:
            shadow_customers += 1
        else:
            rules_only_customers += 1
        published_response = await service_request(
            "POST",
            f"{url_for('rule_engine')}/internal/v1/rules/evaluate",
            correlation_id=correlation_id(request),
            json={
                "customerId": customer_id,
                "metrics": rule_engine_metrics(
                    metrics,
                    flow_visibility=customer.get("flowVisibility"),
                    banking_relationship=customer.get("bankingRelationship"),
                    declared_turnover_growth_rate=float(
                        customer.get("declaredTurnoverGrowthRate") or 0
                    ),
                    no_recent_domiciliation_action=context.facts.get(
                        "no_recent_domiciliation_action", True
                    )
                    is True,
                ),
            },
            incoming_authorization=request.headers.get("Authorization"),
        )
        published = rule_engine_candidates(
            customer_id,
            payload.asOf,
            published_response,
            flow_visibility_level=context.flow_visibility_level,
        )
        governed_types = {candidate.opportunity_type for candidate in published}
        base_candidates = [
            *(
                candidate
                for candidate in engine.evaluate(context)
                if candidate.opportunity_type not in governed_types
            ),
            *published,
        ]
        candidates = [rules_only_candidate(candidate) for candidate in base_candidates]
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
                            "lifecycle": candidate.lifecycle_policy,
                            "evidence": [
                                item.model_dump(mode="json") for item in candidate.evidence
                            ],
                        }
                    ),
                    active=True,
                    created_by="opportunity-service",
                )
                if candidate.rule_set_version == "rule-studio":
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
            recommendations = hydrate_recommended_products(
                candidate.recommended_products,
                catalog,
            )
            evidence = [item.model_dump(mode="json") for item in candidate.evidence]
            candidate_policy = lifecycle_policy(candidate.lifecycle_policy)
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
                    "reason": item.get("reason"),
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
                "flowVisibility": customer.get("flowVisibility"),
                "recommendationNature": candidate.recommendation_nature,
                "recommendedProducts": recommendations,
                "horizon": candidate.horizon,
                "engineVersion": candidate.engine_version,
                "ruleVersion": candidate.rule_version,
                "evidence": evidence,
                "audit": {
                    "ruleSetVersion": candidate.rule_set_version,
                    "correlationId": correlation_id(request),
                },
                "propensityShadow": shadow_propensity,
                "combination": {
                    "method": "RULES_ONLY",
                    "mlObservationMode": ml_result.mode.value,
                    "policyId": policy.policy_id,
                    "policyVersion": policy_version.version,
                    "mlWeight": 0.0,
                    "rulesWeight": 1.0,
                    "configuredMlWeight": ml_weight,
                    "configuredRulesWeight": rules_weight,
                    "fallbackCause": ml_result.cause.as_dict() if ml_result.cause else None,
                    "commercialUseOnly": True,
                    "shadowReadOnly": True,
                },
            }
            customer_uuid = deterministic_uuid("customer", customer_id)
            decision, terminal, active = classify_generation(
                session,
                customer_id=customer_uuid,
                opportunity_type=candidate.opportunity_type,
                as_of=generation_time,
            )
            opportunity_id = (
                terminal.id
                if terminal is not None
                else active.id
                if active is not None
                else deterministic_uuid("opportunity-row", candidate.opportunity_id)
            )
            opportunity_ref = (
                terminal.opportunity_ref
                if terminal is not None
                else active.opportunity_ref
                if active is not None
                else candidate.opportunity_id
            )
            values = {
                "id": opportunity_id,
                "opportunity_ref": opportunity_ref,
                "customer_id": customer_uuid,
                "customer_ref": customer_id,
                "customer_name": customer["legalName"],
                "opportunity_type": candidate.opportunity_type,
                "status": active.status if active is not None else candidate.status,
                "status_updated_at": (
                    active.status_updated_at if active is not None else generation_time
                ),
                "status_reason": (
                    active.status_reason if active is not None else "Opportunity generated"
                ),
                "expires_at": generation_time + timedelta(days=candidate_policy["validity_days"]),
                "cooldown_until": None,
                "last_action_at": active.last_action_at if active is not None else None,
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
                "recommendation_nature": candidate.recommendation_nature,
                "explanation_json": explanation,
                "generated_at": generation_time,
                "engine_version": candidate.engine_version,
                "rule_version": candidate.rule_version,
                "scoring_policy_id": policy.policy_id,
                "scoring_policy_version": policy_version.version,
                "rules_weight": Decimal("1"),
                "ml_weight": Decimal("0"),
                "fallback_mode": "RULES_ONLY",
                "fallback_cause_json": (ml_result.cause.as_dict() if ml_result.cause else None),
                "rule_id": rule.id,
                "deduplication_key": (
                    f"{customer_id}:{candidate.opportunity_type}:"
                    f"{payload.asOf}:{candidate.rule_version}"
                ),
                "created_by": "opportunity-service",
            }
            if decision == "CREATED":
                session.add(Opportunity(**values))
                created += 1
            elif decision == "REFRESHED" and active is not None:
                for key, value in values.items():
                    if key not in {
                        "id",
                        "opportunity_ref",
                        "created_by",
                        "status",
                        "status_updated_at",
                        "status_reason",
                        "last_action_at",
                        "deduplication_key",
                    }:
                        setattr(active, key, value)
                refreshed += 1
            else:
                suppressed += 1
            session.flush()
            for position, item in enumerate(candidate.evidence if decision != "SUPPRESSED" else ()):
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
                            "opportunity-evidence", opportunity_id, payload.asOf, position
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
                decision_id=(
                    f"{candidate.opportunity_id}:{decision}:{idempotency_key}:"
                    f"{candidate.opportunity_type}"
                ),
                opportunity={
                    "type": candidate.opportunity_type,
                    "what": candidate.what,
                    "decision": decision,
                },
                inputs={
                    "metrics": metrics,
                    "signals": signals,
                    "propensityShadow": shadow_propensity,
                    "scoringPolicy": {
                        "policyId": policy.policy_id,
                        "version": policy_version.version,
                    },
                    "fallback": ml_result.audit_event.as_dict(),
                    "lifecycle": {
                        "policy": candidate_policy,
                        "activeOpportunityId": (
                            active.opportunity_ref if active is not None else None
                        ),
                        "terminalOpportunityId": (
                            terminal.opportunity_ref if terminal is not None else None
                        ),
                        "cooldownUntil": (
                            terminal.cooldown_until.isoformat()
                            if terminal is not None and terminal.cooldown_until is not None
                            else None
                        ),
                    },
                },
                config_id=config.config_id,
                config_checksum=config.checksum(),
                correlation_id=correlation_id(request),
            )
            session.add(
                AuditLog(
                    id=deterministic_uuid(
                        "opportunity-generation-audit",
                        candidate.opportunity_id,
                        decision,
                        idempotency_key,
                        candidate.opportunity_type,
                    ),
                    occurred_at=datetime.now(timezone.utc),
                    actor_subject_id=principal.subject,
                    service_name="opportunity-service",
                    action=f"OPPORTUNITY_GENERATION_{decision}",
                    resource_type="OPPORTUNITY_GENERATION",
                    resource_id=candidate.opportunity_id,
                    correlation_id=correlation_id(request),
                    result="SUCCESS",
                    metadata_json={
                        "decision": decision,
                        "customerId": customer_id,
                        "opportunityType": candidate.opportunity_type,
                        "candidateOpportunityId": candidate.opportunity_id,
                        "activeOpportunityId": (
                            active.opportunity_ref if active is not None else None
                        ),
                        "terminalOpportunityId": (
                            terminal.opportunity_ref if terminal is not None else None
                        ),
                        "cooldownUntil": (
                            terminal.cooldown_until.isoformat()
                            if terminal is not None and terminal.cooldown_until is not None
                            else None
                        ),
                        "lifecyclePolicy": candidate_policy,
                        "ruleVersion": candidate.rule_version,
                        "engineVersion": candidate.engine_version,
                        "fallbackMode": "RULES_ONLY",
                        "mlObservationMode": ml_result.mode.value,
                    },
                )
            )
            session.execute(
                pg_insert(DecisionAudit)
                .values(
                    id=deterministic_uuid("decision-audit", audit["decision_hash"]),
                    opportunity_id=opportunity_id,
                    customer_id=customer_uuid,
                    engine_version=candidate.engine_version,
                    rule_version=candidate.rule_version,
                    generated_at=generation_time,
                    input_reference=f"metrics:{payload.asOf}",
                    signals_json=signals,
                    metric_snapshots_json=metrics,
                    confidence_components_json=list(candidate.confidence_components),
                    priority_components_json=list(candidate.priority_components),
                    scoring_policy_id=policy.policy_id,
                    scoring_policy_version=policy_version.version,
                    fallback_mode="RULES_ONLY",
                    fallback_cause_json=(ml_result.cause.as_dict() if ml_result.cause else None),
                    decision_hash=audit["decision_hash"],
                )
                .on_conflict_do_nothing(index_elements=[DecisionAudit.decision_hash])
            )
    # Le statut COMPLETED garantit que dashboards, E2E et lot suivant voient les écritures.
    session.commit()
    return {
        "jobId": str(deterministic_uuid("opportunity-job", idempotency_key)),
        "status": "COMPLETED",
        "opportunities": created + refreshed,
        "created": created,
        "refreshed": refreshed,
        "suppressed": suppressed,
        "expired": expired,
        "customers": len(payload.customerIds),
        "asOf": payload.asOf.isoformat(),
        "ruleSetVersion": config.rule_set_version,
        "scoringPolicy": {
            "policyId": policy.policy_id,
            "version": policy_version.version,
            "rulesWeight": 1.0,
            "mlWeight": 0.0,
            "configuredRulesWeight": rules_weight,
            "configuredMlWeight": ml_weight,
        },
        "executionModes": {
            "POC_SHADOW": shadow_customers,
            "RULES_ONLY": rules_only_customers,
        },
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

    def editable_parameters(row: OpportunityRule) -> dict[str, Any]:
        configuration = dict(row.configuration_json)
        if row.opportunity_type == "FLOW_DOMICILIATION":
            configuration.update(dict(configuration.get("visibility_policy") or {}))
            configuration.pop("visibility_policy", None)
        return configuration

    data = [
        {
            "ruleId": str(row.id),
            "name": row.opportunity_type.replace("_", " ").title(),
            "opportunityType": row.opportunity_type,
            "enabled": row.active,
            "version": row.version,
            "ruleVersion": row.version,
            "parameters": editable_parameters(row),
            "lifecyclePolicy": serialize_lifecycle_policy(row.configuration_json),
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
    parameters: dict[str, Any] | None = None
    justification: str = Field(min_length=3, max_length=1_000)
    effectiveAt: datetime | None = None


@app.patch(
    f"{PREFIX}/admin/rules/{{rule_id}}",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Administration"],
)
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        parsed_rule_id = UUID(rule_id)
    except ValueError:
        raise not_found("Rule") from None
    row = session.get(OpportunityRule, parsed_rule_id)
    if row is None:
        raise not_found("Rule")
    if row.opportunity_type == "FLOW_DOMICILIATION" and payload.enabled is True:
        raise Problem(
            409,
            "RULE_STUDIO_PUBLICATION_REQUIRED",
            "FLOW_DOMICILIATION can only become operational through the governed "
            "Rule Studio publication flow.",
        )
    now = datetime.now(timezone.utc)
    if payload.effectiveAt is not None and lifecycle_time(payload.effectiveAt) > now:
        raise Problem(
            422,
            "FUTURE_EFFECTIVE_DATE_UNSUPPORTED",
            "A future effectiveAt requires a scheduler and is not accepted by this endpoint.",
        )
    version = f"{row.version}-v{int(datetime.now(timezone.utc).timestamp())}"
    configuration = dict(row.configuration_json)
    visibility_policy_changed = False
    if payload.parameters is not None:
        parameters = dict(payload.parameters)
        visibility_keys = {
            "highShare",
            "partialShare",
            "fingerprints90d",
            "partialPenaltyPoints",
            "lowPenaltyPoints",
            "unknownPenaltyPoints",
            "domiciliationCooldownDays",
            "status",
        }
        visibility_updates = {
            key: parameters.pop(key) for key in visibility_keys if key in parameters
        }
        if visibility_updates:
            if row.opportunity_type != "FLOW_DOMICILIATION":
                raise Problem(
                    422,
                    "INVALID_RULE_CONFIGURATION",
                    "Visibility policy parameters are reserved for FLOW_DOMICILIATION.",
                )
            visibility_policy = dict(configuration.get("visibility_policy") or {})
            visibility_policy.update(visibility_updates)
            high_share = float(visibility_policy.get("highShare", 0.70))
            partial_share = float(visibility_policy.get("partialShare", 0.30))
            if not 0 <= partial_share <= high_share <= 1:
                raise Problem(
                    422,
                    "INVALID_VISIBILITY_THRESHOLDS",
                    "Visibility shares must satisfy 0 <= partialShare <= highShare <= 1.",
                )
            for key in ("partialPenaltyPoints", "lowPenaltyPoints", "unknownPenaltyPoints"):
                value = int(visibility_policy.get(key, 0))
                if not -100 <= value <= 0:
                    raise Problem(
                        422,
                        "INVALID_VISIBILITY_PENALTY",
                        f"{key} must be between -100 and 0.",
                    )
            if int(visibility_policy.get("fingerprints90d", 2)) < 1:
                raise Problem(
                    422,
                    "INVALID_VISIBILITY_FINGERPRINT_THRESHOLD",
                    "fingerprints90d must be at least 1.",
                )
            if not 1 <= int(visibility_policy.get("domiciliationCooldownDays", 180)) <= 730:
                raise Problem(
                    422,
                    "INVALID_VISIBILITY_COOLDOWN",
                    "domiciliationCooldownDays must be between 1 and 730.",
                )
            configuration["visibility_policy"] = visibility_policy
            visibility_policy_changed = True
        configuration.update(parameters)
    try:
        validated = OpportunityRuleConfig.model_validate(configuration)
    except ValidationError as exc:
        raise Problem(
            422,
            "INVALID_RULE_CONFIGURATION",
            "The merged opportunity rule configuration is invalid.",
            details=[
                {"field": ".".join(map(str, error["loc"])), "message": error["msg"]}
                for error in exc.errors()
            ],
        ) from exc
    configuration = validated.model_dump(mode="json")
    configuration["version"] = version
    configuration["governance"] = {
        "justification": payload.justification,
        "effectiveAt": lifecycle_time(payload.effectiveAt).isoformat()
        if payload.effectiveAt is not None
        else now.isoformat(),
        "updatedBy": principal.subject,
    }
    clone = OpportunityRule(
        id=deterministic_uuid("opp-rule", row.opportunity_type, version),
        opportunity_type=row.opportunity_type,
        version=version,
        configuration_json=configuration,
        active=payload.enabled if payload.enabled is not None else row.active,
        created_by=principal.subject,
    )
    row.active = False
    if row.opportunity_type == "FLOW_DOMICILIATION" and visibility_policy_changed:
        latest_policy_version = session.scalar(select(func.max(FlowVisibilityPolicy.version)))
        policy_version = int(latest_policy_version or 0) + 1
        session.add(
            FlowVisibilityPolicy(
                id=deterministic_uuid("flow-visibility-policy", policy_version),
                policy_id="multibank-flow-visibility",
                version=policy_version,
                active=False,
                configuration_json=dict(configuration.get("visibility_policy") or {}),
                justification=payload.justification,
                created_by=principal.subject,
            )
        )
    session.add(clone)
    session.add(
        AuditLog(
            id=deterministic_uuid("opportunity-rule-audit", clone.id, now.isoformat()),
            occurred_at=now,
            actor_subject_id=principal.subject,
            service_name="opportunity-service",
            action="OPPORTUNITY_RULE_VERSION_CREATED",
            resource_type="OPPORTUNITY_RULE",
            resource_id=str(clone.id),
            correlation_id=correlation_id(request),
            result="SUCCESS",
            metadata_json={
                "previousRuleId": str(row.id),
                "version": version,
                "justification": payload.justification,
            },
        )
    )
    return {
        "ruleId": str(clone.id),
        "name": clone.opportunity_type.replace("_", " ").title(),
        "opportunityType": clone.opportunity_type,
        "enabled": clone.active,
        "version": clone.version,
        "ruleVersion": clone.version,
        "parameters": clone.configuration_json,
        "updatedAt": now.isoformat(),
        "updatedBy": principal.subject,
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
