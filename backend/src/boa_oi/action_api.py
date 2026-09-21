from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, time, timezone
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.http_clients import service_request
from boa_oi.models.entities import ActionOutcome, AuditLog, OpportunityAction, OutboxMessage
from boa_oi.platform import (
    COMMERCIAL_ROLES,
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
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "action-service", "RM actions, engagement outcomes, idempotency and feedback KPIs."
)
PREFIX = "/internal/v1"
ACTION_TYPES = {
    "ACCEPT_OPPORTUNITY",
    "DISMISS_OPPORTUNITY",
    "CONTACT_CUSTOMER",
    "CREATE_FOLLOW_UP",
    "DEFER_OPPORTUNITY",
    "SCHEDULE_MEETING",
    "MARK_CONVERTED",
}
OUTCOMES = {
    "CONTACTED",
    "MEETING_SCHEDULED",
    "OFFER_CREATED",
    "CONVERTED",
    "REJECTED",
    "NOT_RELEVANT",
    "REVIEW_LATER",
}
ACTION_STATUS_TRANSITIONS = {
    "OPEN": {"IN_PROGRESS", "COMPLETED", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}
OPPORTUNITY_STATUS_BY_ACTION = {
    "ACCEPT_OPPORTUNITY": "ACCEPTED",
    "DISMISS_OPPORTUNITY": "DISMISSED",
    "DEFER_OPPORTUNITY": "DEFERRED",
    "MARK_CONVERTED": "CONVERTED",
}
OPPORTUNITY_STATUS_BY_OUTCOME = {
    "CONTACTED": "CONTACTED",
    "MEETING_SCHEDULED": "CONTACTED",
    "OFFER_CREATED": "CONTACTED",
    "CONVERTED": "CONVERTED",
    "REJECTED": "DISMISSED",
    "NOT_RELEVANT": "DISMISSED",
    "REVIEW_LATER": "DEFERRED",
}
OUTCOME_BY_TERMINAL_ACTION = {
    "DISMISS_OPPORTUNITY": "NOT_RELEVANT",
    "DEFER_OPPORTUNITY": "REVIEW_LATER",
    "MARK_CONVERTED": "CONVERTED",
}
NOTIFIABLE_ACTION_TYPES = {"CONTACT_CUSTOMER", "SCHEDULE_MEETING", "DEFER_OPPORTUNITY"}


class CreateAction(BaseModel):
    opportunityId: str
    customerId: str
    actionType: Literal[
        "ACCEPT_OPPORTUNITY",
        "DISMISS_OPPORTUNITY",
        "CONTACT_CUSTOMER",
        "CREATE_FOLLOW_UP",
        "DEFER_OPPORTUNITY",
        "SCHEDULE_MEETING",
        "MARK_CONVERTED",
    ]
    dueAt: datetime | None = None
    note: str | None = Field(default=None, max_length=4_000)


class UpdateAction(BaseModel):
    status: Literal["OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"] | None = None
    outcome: (
        Literal[
            "CONTACTED",
            "MEETING_SCHEDULED",
            "OFFER_CREATED",
            "CONVERTED",
            "REJECTED",
            "NOT_RELEVANT",
            "REVIEW_LATER",
        ]
        | None
    ) = None
    dueAt: datetime | None = None
    note: str | None = Field(default=None, max_length=4_000)


def opportunity_url() -> str:
    value = os.getenv("OPPORTUNITY_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            "OPPORTUNITY_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def customer_url() -> str:
    value = os.getenv("CUSTOMER_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            "CUSTOMER_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def serialize(item: OpportunityAction) -> dict[str, Any]:
    return {
        "actionId": item.action_ref,
        "opportunityId": item.opportunity_ref,
        "opportunityType": item.opportunity_type,
        "customerId": item.customer_ref,
        "actionType": item.action_type,
        "status": item.status,
        "assignedTo": item.assigned_to,
        "dueAt": item.due_at.isoformat() if item.due_at else None,
        "note": item.notes_redacted,
        "outcome": item.outcome_type,
        "transitionStatus": item.transition_status,
        "transitionError": item.transition_error,
        "createdAt": item.created_at.isoformat(),
        "createdBy": item.actor_subject_id,
        "updatedAt": item.updated_at.isoformat()
        if item.updated_at
        else item.created_at.isoformat(),
    }


def _audit_action(
    session: Session,
    *,
    item: OpportunityAction,
    principal: Principal,
    request: Request,
    event: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    occurred_at = datetime.now(timezone.utc)
    session.add(
        AuditLog(
            id=deterministic_uuid(
                "action-audit",
                item.action_ref,
                event,
                correlation_id(request),
                occurred_at.isoformat(),
            ),
            occurred_at=occurred_at,
            actor_subject_id=principal.subject,
            service_name="action-service",
            action=event,
            resource_type="OPPORTUNITY_ACTION",
            resource_id=item.action_ref,
            correlation_id=correlation_id(request),
            result="SUCCESS",
            metadata_json={"before": before, "after": after},
        )
    )


def _queue_action_notification(
    session: Session,
    *,
    item: OpportunityAction,
    principal: Principal,
    request: Request,
    ready: bool = True,
) -> None:
    if (
        item.action_type not in NOTIFIABLE_ACTION_TYPES
        or item.due_at is None
        or not principal.email
        or not principal.email_verified
    ):
        return
    event_id = deterministic_uuid("action-notification", item.action_ref)
    existing = session.get(OutboxMessage, event_id)
    if existing is not None:
        if ready:
            existing.processing_status = "READY"
            existing.processing_error = None
        return
    session.add(
        OutboxMessage(
            id=event_id,
            event_type="ACTION_NOTIFICATION_REQUESTED",
            aggregate_type="OPPORTUNITY_ACTION",
            aggregate_id=item.action_ref,
            payload_json={
                "actionId": item.action_ref,
                "actionType": item.action_type,
                "opportunityId": item.opportunity_ref,
                "customerId": item.customer_ref,
                "dueAt": item.due_at.isoformat(),
                "recipientEmail": principal.email,
                "recipientName": principal.username or principal.subject,
            },
            correlation_id=correlation_id(request),
            causation_id=item.idempotency_key,
            occurred_at=datetime.now(timezone.utc),
            processing_status="READY" if ready else "BLOCKED",
        )
    )


def _validate_action_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = ACTION_STATUS_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise Problem(
            409,
            "INVALID_ACTION_TRANSITION",
            f"Action status cannot transition from {current} to {target}.",
        )


async def _transition_opportunity(
    request: Request,
    *,
    opportunity_id: str,
    target_status: str,
    reason: str,
    actor_subject_id: str,
    command_id: str,
    cooldown_until: datetime | None = None,
) -> None:
    body: dict[str, Any] = {
        "status": target_status,
        "reason": reason,
        "actorSubjectId": actor_subject_id,
    }
    if cooldown_until is not None:
        body["cooldownUntil"] = cooldown_until.isoformat()
    await service_request(
        "POST",
        f"{opportunity_url()}/internal/v1/opportunities/{opportunity_id}/transition",
        correlation_id=correlation_id(request),
        json=body,
        idempotency_key=command_id,
    )


async def _assert_resource_scope(
    request: Request,
    principal: Principal,
    *,
    opportunity_id: str | None = None,
    customer_id: str | None = None,
) -> None:
    if {"ADMIN", "SERVICE", "DATA_ANALYST"} & principal.roles:
        return
    authorization = request.headers.get("Authorization")
    if opportunity_id is not None:
        await service_request(
            "GET",
            f"{opportunity_url()}/internal/v1/opportunities/{opportunity_id}",
            correlation_id=correlation_id(request),
            incoming_authorization=authorization,
        )
        return
    if customer_id is not None:
        await service_request(
            "GET",
            f"{customer_url()}/internal/v1/customers/{customer_id}",
            correlation_id=correlation_id(request),
            incoming_authorization=authorization,
        )


def _record_transition_failure(
    session: Session,
    *,
    item: OpportunityAction,
    principal: Principal,
    request: Request,
    problem: Problem,
) -> None:
    item.transition_status = "FAILED"
    item.transition_error = problem.code
    item.updated_at = datetime.now(timezone.utc)
    session.add(
        AuditLog(
            id=deterministic_uuid(
                "action-transition-failure",
                item.transition_command_id,
                item.transition_attempt_count,
            ),
            occurred_at=item.updated_at,
            actor_subject_id=principal.subject,
            service_name="action-service",
            action="OPPORTUNITY_TRANSITION_FAILED",
            resource_type="OPPORTUNITY_ACTION",
            resource_id=item.action_ref,
            correlation_id=correlation_id(request),
            result="FAILED",
            metadata_json={
                "targetStatus": item.transition_target,
                "commandId": item.transition_command_id,
                "attempt": item.transition_attempt_count,
                "code": problem.code,
            },
        )
    )


def _finalize_transition(
    session: Session,
    *,
    item: OpportunityAction,
    principal: Principal,
    request: Request,
) -> None:
    before = serialize(item)
    pending_outcome = item.pending_outcome_type
    item.transition_status = "APPLIED"
    item.transition_error = None
    item.pending_outcome_type = None
    item.status = "COMPLETED"
    item.performed_at = datetime.now(timezone.utc)
    item.updated_at = item.performed_at
    if pending_outcome is not None:
        item.outcome_type = pending_outcome
        outcome_id = deterministic_uuid("outcome", item.action_ref, pending_outcome)
        if session.get(ActionOutcome, outcome_id) is None:
            session.add(
                ActionOutcome(
                    id=outcome_id,
                    action_id=item.id,
                    outcome_type=pending_outcome,
                    recorded_by=principal.subject,
                    correlation_id=correlation_id(request),
                    metadata_json={"source": "transition-saga"},
                )
            )
    _audit_action(
        session,
        item=item,
        principal=principal,
        request=request,
        event="OPPORTUNITY_TRANSITION_APPLIED",
        before=before,
        after=serialize(item),
    )
    _queue_action_notification(
        session,
        item=item,
        principal=principal,
        request=request,
    )


async def _run_transition_command(
    session: Session,
    *,
    item: OpportunityAction,
    principal: Principal,
    request: Request,
) -> None:
    if item.transition_target is None or item.transition_command_id is None:
        return
    item.transition_status = "PENDING"
    item.transition_error = None
    item.transition_attempt_count += 1
    item.transition_requested_at = datetime.now(timezone.utc)
    item.updated_at = item.transition_requested_at
    session.flush()
    session.commit()
    pending_outcome = item.pending_outcome_type
    reason = (
        f"Commercial action {item.action_type} by {item.actor_subject_id}"
        if item.transition_command_id.startswith("action-create:")
        else f"Commercial outcome {pending_outcome} by {item.actor_subject_id}"
    )
    try:
        await _transition_opportunity(
            request,
            opportunity_id=item.opportunity_ref,
            target_status=item.transition_target,
            reason=reason,
            actor_subject_id=item.actor_subject_id,
            command_id=item.transition_command_id,
            cooldown_until=item.due_at if item.transition_target == "DEFERRED" else None,
        )
    except Problem as problem:
        _record_transition_failure(
            session,
            item=item,
            principal=principal,
            request=request,
            problem=problem,
        )
        session.commit()
        raise
    _finalize_transition(session, item=item, principal=principal, request=request)


def list_for(
    request: Request,
    session: Session,
    principal: Principal,
    *,
    opportunity_id: str | None = None,
    customer_id: str | None = None,
    page_size: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "opportunityId",
            "customerId",
            "actionType",
            "outcome",
            "assignedTo",
            "fromDate",
            "toDate",
            "sort",
        },
    )
    params = request.query_params
    offset = decode_cursor(cursor)
    stmt = select(OpportunityAction)
    if not ({"ADMIN", "SERVICE", "DATA_ANALYST"} & principal.roles):
        if "RELATIONSHIP_MANAGER" in principal.roles:
            stmt = stmt.where(OpportunityAction.actor_subject_id == principal.subject)
        elif "BRANCH_MANAGER" in principal.roles and not (opportunity_id or customer_id):
            raise Problem(
                403,
                "SCOPED_DASHBOARD_REQUIRED",
                "Branch actions must be consulted through the scoped branch dashboard.",
            )
    target_opp = opportunity_id or params.get("opportunityId")
    target_customer = customer_id or params.get("customerId")
    if target_opp:
        stmt = stmt.where(OpportunityAction.opportunity_ref == target_opp)
    if target_customer:
        stmt = stmt.where(OpportunityAction.customer_ref == target_customer)
    if params.get("actionType"):
        stmt = stmt.where(OpportunityAction.action_type == params["actionType"])
    if params.get("outcome"):
        stmt = stmt.where(OpportunityAction.outcome_type == params["outcome"])
    if params.get("assignedTo"):
        stmt = stmt.where(OpportunityAction.assigned_to == params["assignedTo"])
    if params.get("fromDate"):
        stmt = stmt.where(
            OpportunityAction.created_at
            >= datetime.combine(
                date.fromisoformat(params["fromDate"]), time.min, tzinfo=timezone.utc
            )
        )
    if params.get("toDate"):
        stmt = stmt.where(
            OpportunityAction.created_at
            < datetime.combine(date.fromisoformat(params["toDate"]), time.min, tzinfo=timezone.utc)
        )
    sort = params.get("sort", "-createdAt")
    column = {
        "createdAt": OpportunityAction.created_at,
        "dueAt": OpportunityAction.due_at,
        "actionType": OpportunityAction.action_type,
    }.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported action sort field.")
    rows = list(
        session.scalars(
            stmt.order_by(
                column.desc() if sort.startswith("-") else column.asc(),
                OpportunityAction.id,
            )
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
    f"{PREFIX}/actions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Actions"],
)
async def list_actions(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await _assert_resource_scope(
        request,
        principal,
        opportunity_id=request.query_params.get("opportunityId"),
        customer_id=request.query_params.get("customerId"),
    )
    return list_for(request, session, principal, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/actions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Actions"],
)
async def opportunity_actions(
    opportunity_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 100,
    cursor: str | None = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await _assert_resource_scope(request, principal, opportunity_id=opportunity_id)
    return list_for(
        request,
        session,
        principal,
        opportunity_id=opportunity_id,
        page_size=page_size,
        cursor=cursor,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/actions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Actions"],
)
async def customer_actions(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 100,
    cursor: str | None = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await _assert_resource_scope(request, principal, customer_id=customer_id)
    return list_for(
        request,
        session,
        principal,
        customer_id=customer_id,
        page_size=page_size,
        cursor=cursor,
    )


@app.post(
    f"{PREFIX}/actions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*COMMERCIAL_ROLES))],
    tags=["Actions"],
)
async def create_action(
    payload: CreateAction,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    body_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    existing = session.scalar(
        select(OpportunityAction).where(OpportunityAction.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.request_hash != body_hash:
            raise Problem(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was reused with different content.",
            )
        await _assert_resource_scope(
            request,
            principal,
            opportunity_id=existing.opportunity_ref,
        )
        if existing.transition_status in {"PENDING", "FAILED"}:
            await _run_transition_command(
                session,
                item=existing,
                principal=principal,
                request=request,
            )
        _queue_action_notification(
            session,
            item=existing,
            principal=principal,
            request=request,
        )
        return serialize(existing)
    corr = correlation_id(request)
    opportunity = await service_request(
        "GET",
        f"{opportunity_url()}/internal/v1/opportunities/{payload.opportunityId}",
        correlation_id=corr,
        incoming_authorization=request.headers.get("Authorization"),
    )
    if opportunity["customerId"] != payload.customerId:
        raise Problem(
            422,
            "VALIDATION_ERROR",
            "The action customer does not match the opportunity.",
        )
    previous = list(
        session.scalars(
            select(OpportunityAction).where(
                OpportunityAction.opportunity_ref == payload.opportunityId
            )
        )
    )
    if payload.actionType in {
        "ACCEPT_OPPORTUNITY",
        "DISMISS_OPPORTUNITY",
        "DEFER_OPPORTUNITY",
        "MARK_CONVERTED",
    } and any(
        item.action_type == payload.actionType
        and (item.status == "COMPLETED" or item.transition_status in {"PENDING", "FAILED"})
        for item in previous
    ):
        raise Problem(
            409,
            "DUPLICATE_ACTION",
            "This terminal commercial action is already recorded for the opportunity.",
        )
    if payload.actionType == "MARK_CONVERTED" and not any(
        item.action_type in {"CONTACT_CUSTOMER", "SCHEDULE_MEETING"}
        or item.outcome_type in {"CONTACTED", "MEETING_SCHEDULED", "OFFER_CREATED"}
        for item in previous
    ):
        raise Problem(
            409,
            "STATE_CONFLICT",
            "Conversion requires a prior customer engagement action.",
        )
    if payload.actionType == "DEFER_OPPORTUNITY":
        if payload.dueAt is None or payload.dueAt.tzinfo is None:
            raise Problem(
                422,
                "VALIDATION_ERROR",
                "DEFER_OPPORTUNITY requires a timezone-aware dueAt.",
            )
        if payload.dueAt <= datetime.now(timezone.utc):
            raise Problem(
                422,
                "VALIDATION_ERROR",
                "DEFER_OPPORTUNITY dueAt must be in the future.",
            )
    target_opportunity_status = OPPORTUNITY_STATUS_BY_ACTION.get(payload.actionType)
    action_ref = str(deterministic_uuid("action", idempotency_key))
    transition_command_id = (
        f"action-create:{action_ref}:{target_opportunity_status}"
        if target_opportunity_status is not None
        else None
    )
    item = OpportunityAction(
        id=deterministic_uuid("action-row", action_ref),
        action_ref=action_ref,
        opportunity_id=deterministic_uuid("opportunity-row", payload.opportunityId),
        opportunity_ref=payload.opportunityId,
        opportunity_type=str(opportunity.get("opportunityType") or "") or None,
        customer_id=deterministic_uuid("customer", payload.customerId),
        customer_ref=payload.customerId,
        action_type=payload.actionType,
        status="IN_PROGRESS" if target_opportunity_status is not None else "OPEN",
        actor_subject_id=principal.subject,
        assigned_to=principal.username or principal.subject,
        scheduled_at=payload.dueAt,
        due_at=payload.dueAt,
        performed_at=None,
        notes_redacted=payload.note,
        outcome_type=None,
        transition_status="PENDING" if target_opportunity_status is not None else "NOT_REQUIRED",
        transition_target=target_opportunity_status,
        transition_command_id=transition_command_id,
        transition_attempt_count=0,
        transition_error=None,
        transition_requested_at=None,
        pending_outcome_type=OUTCOME_BY_TERMINAL_ACTION.get(payload.actionType),
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        correlation_id=corr,
    )
    session.add(item)
    session.flush()
    _audit_action(
        session,
        item=item,
        principal=principal,
        request=request,
        event="ACTION_CREATED",
        before=None,
        after=serialize(item),
    )
    if target_opportunity_status is not None:
        _queue_action_notification(
            session,
            item=item,
            principal=principal,
            request=request,
            ready=False,
        )
        await _run_transition_command(
            session,
            item=item,
            principal=principal,
            request=request,
        )
    else:
        _queue_action_notification(
            session,
            item=item,
            principal=principal,
            request=request,
        )
    return serialize(item)


@app.patch(
    f"{PREFIX}/actions/{{action_id}}",
    dependencies=[Depends(require_roles(*COMMERCIAL_ROLES))],
    tags=["Actions"],
)
async def update_action(
    action_id: str,
    payload: UpdateAction,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.scalar(
        select(OpportunityAction).where(OpportunityAction.action_ref == action_id)
    )
    if item is None:
        raise not_found("Action")
    await _assert_resource_scope(request, principal, opportunity_id=item.opportunity_ref)
    if item.transition_status in {"PENDING", "FAILED"}:
        if payload.outcome is not None and payload.outcome == item.pending_outcome_type:
            await _run_transition_command(
                session,
                item=item,
                principal=principal,
                request=request,
            )
            return serialize(item)
        raise Problem(
            409,
            "ACTION_TRANSITION_PENDING",
            "A previous opportunity transition must be resumed before another update.",
        )
    before = serialize(item)
    target_status = "COMPLETED" if payload.outcome is not None else payload.status
    if target_status is not None:
        _validate_action_transition(item.status, target_status)
    outcome_changed = payload.outcome is not None and item.outcome_type != payload.outcome
    if payload.outcome is not None and item.outcome_type not in {None, payload.outcome}:
        raise Problem(
            409,
            "OUTCOME_CONFLICT",
            "A terminal commercial outcome cannot be replaced by another outcome.",
        )
    if payload.status is not None:
        item.status = payload.status
    if payload.dueAt is not None:
        item.due_at = payload.dueAt
    if payload.note is not None:
        item.notes_redacted = payload.note
    if payload.outcome is not None and outcome_changed:
        item.status = "IN_PROGRESS"
        item.transition_status = "PENDING"
        item.transition_target = OPPORTUNITY_STATUS_BY_OUTCOME[payload.outcome]
        item.transition_command_id = f"action-outcome:{item.action_ref}:{payload.outcome}"
        item.pending_outcome_type = payload.outcome
        item.transition_error = None
    elif payload.outcome is not None:
        item.status = "COMPLETED"
    item.updated_at = datetime.now(timezone.utc)
    session.flush()
    after = serialize(item)
    if after != before:
        _audit_action(
            session,
            item=item,
            principal=principal,
            request=request,
            event="ACTION_UPDATED",
            before=before,
            after=after,
        )
    if payload.outcome is not None and outcome_changed:
        await _run_transition_command(
            session,
            item=item,
            principal=principal,
            request=request,
        )
    return serialize(item)


@app.get(
    f"{PREFIX}/metrics/dashboard",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Actions"],
)
async def dashboard(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    opportunities = await service_request(
        "GET",
        f"{opportunity_url()}/internal/v1/opportunities",
        correlation_id=correlation_id(request),
        params={"pageSize": 1000},
        incoming_authorization=request.headers.get("Authorization"),
    )
    rows = opportunities["data"]
    actions = list(session.scalars(select(OpportunityAction)))
    total = len(rows)
    contacted = len(
        {
            item.opportunity_ref
            for item in actions
            if item.action_type == "CONTACT_CUSTOMER" or item.outcome_type == "CONTACTED"
        }
    )
    converted = len(
        {
            item.opportunity_ref
            for item in actions
            if item.action_type == "MARK_CONVERTED" or item.outcome_type == "CONVERTED"
        }
    )
    dismissed = len(
        {
            item.opportunity_ref
            for item in actions
            if item.action_type == "DISMISS_OPPORTUNITY"
            or item.outcome_type in {"REJECTED", "NOT_RELEVANT"}
        }
    )
    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for item in rows:
        by_type[item["opportunityType"]] = by_type.get(item["opportunityType"], 0) + 1
        by_priority[item["priorityLevel"]] = by_priority.get(item["priorityLevel"], 0) + 1
    return {
        "totalOpportunities": total,
        "todaysOpportunities": sum(
            1
            for item in rows
            if item["generatedAt"][:10] == datetime.now(timezone.utc).date().isoformat()
        ),
        "highConfidenceOpportunities": sum(1 for item in rows if item["confidenceLevel"] == "HIGH"),
        "contactedOpportunities": contacted,
        "contactRate": contacted / total if total else 0,
        "conversionRate": converted / total if total else 0,
        "dismissalRate": dismissed / total if total else 0,
        "falsePositiveRate": dismissed / total if total else 0,
        "opportunitiesByType": [
            {"opportunityType": key, "count": value} for key, value in sorted(by_type.items())
        ],
        "opportunitiesByPriority": [
            {"priorityLevel": key, "count": value} for key, value in sorted(by_priority.items())
        ],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


__all__ = ["app"]
