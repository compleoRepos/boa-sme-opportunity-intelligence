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
from boa_oi.models.entities import ActionOutcome, OpportunityAction
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
}


class CreateAction(BaseModel):
    opportunityId: str
    customerId: str
    actionType: Literal[
        "ACCEPT_OPPORTUNITY",
        "DISMISS_OPPORTUNITY",
        "CONTACT_CUSTOMER",
        "CREATE_FOLLOW_UP",
        "SCHEDULE_MEETING",
        "MARK_CONVERTED",
    ]
    dueAt: datetime | None = None
    note: str | None = Field(default=None, max_length=4_000)


class UpdateAction(BaseModel):
    status: str | None = None
    outcome: (
        Literal[
            "CONTACTED",
            "MEETING_SCHEDULED",
            "OFFER_CREATED",
            "CONVERTED",
            "REJECTED",
            "NOT_RELEVANT",
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


def serialize(item: OpportunityAction) -> dict[str, Any]:
    return {
        "actionId": item.action_ref,
        "opportunityId": item.opportunity_ref,
        "customerId": item.customer_ref,
        "actionType": item.action_type,
        "status": item.status,
        "assignedTo": item.assigned_to,
        "dueAt": item.due_at.isoformat() if item.due_at else None,
        "note": item.notes_redacted,
        "outcome": item.outcome_type,
        "createdAt": item.created_at.isoformat(),
        "createdBy": item.actor_subject_id,
        "updatedAt": item.updated_at.isoformat()
        if item.updated_at
        else item.created_at.isoformat(),
    }


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
def list_actions(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return list_for(request, session, principal, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/opportunities/{{opportunity_id}}/actions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Actions"],
)
def opportunity_actions(
    opportunity_id: str,
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
        opportunity_id=opportunity_id,
        page_size=page_size,
        cursor=cursor,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/actions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Actions"],
)
def customer_actions(
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
    action_ref = str(deterministic_uuid("action", idempotency_key))
    item = OpportunityAction(
        id=deterministic_uuid("action-row", action_ref),
        action_ref=action_ref,
        opportunity_id=deterministic_uuid("opportunity-row", payload.opportunityId),
        opportunity_ref=payload.opportunityId,
        customer_id=deterministic_uuid("customer", payload.customerId),
        customer_ref=payload.customerId,
        action_type=payload.actionType,
        status="COMPLETED"
        if payload.actionType in {"ACCEPT_OPPORTUNITY", "DISMISS_OPPORTUNITY", "MARK_CONVERTED"}
        else "OPEN",
        actor_subject_id=principal.subject,
        assigned_to=principal.username or principal.subject,
        scheduled_at=payload.dueAt,
        due_at=payload.dueAt,
        performed_at=datetime.now(timezone.utc)
        if payload.actionType in {"ACCEPT_OPPORTUNITY", "DISMISS_OPPORTUNITY", "MARK_CONVERTED"}
        else None,
        notes_redacted=payload.note,
        outcome_type="CONVERTED"
        if payload.actionType == "MARK_CONVERTED"
        else ("NOT_RELEVANT" if payload.actionType == "DISMISS_OPPORTUNITY" else None),
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        correlation_id=corr,
    )
    session.add(item)
    if item.outcome_type:
        session.add(
            ActionOutcome(
                id=deterministic_uuid("outcome", action_ref, item.outcome_type),
                action_id=item.id,
                outcome_type=item.outcome_type,
                recorded_by=principal.subject,
                correlation_id=corr,
                metadata_json={"source": "action-create"},
            )
        )
    session.flush()
    return serialize(item)


@app.patch(
    f"{PREFIX}/actions/{{action_id}}",
    dependencies=[Depends(require_roles(*COMMERCIAL_ROLES))],
    tags=["Actions"],
)
def update_action(
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
    if payload.status is not None:
        item.status = payload.status
    if payload.dueAt is not None:
        item.due_at = payload.dueAt
    if payload.note is not None:
        item.notes_redacted = payload.note
    if payload.outcome is not None:
        item.outcome_type = payload.outcome
        item.status = "COMPLETED"
        item.performed_at = datetime.now(timezone.utc)
        session.add(
            ActionOutcome(
                id=deterministic_uuid(
                    "outcome",
                    item.action_ref,
                    payload.outcome,
                    datetime.now(timezone.utc).isoformat(),
                ),
                action_id=item.id,
                outcome_type=payload.outcome,
                recorded_by=principal.subject,
                correlation_id=correlation_id(request),
                metadata_json={"source": "action-update"},
            )
        )
    item.updated_at = datetime.now(timezone.utc)
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
