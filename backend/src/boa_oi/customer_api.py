from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, case, func, inspect, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from boa_oi.audit.service import canonical_hash
from boa_oi.models.entities import (
    AuditLog,
    Customer,
    CustomerBankingDeclaration,
    CustomerImportReceipt,
    FlowVisibilitySnapshot,
    OutboxMessage,
    PortfolioAssignment,
    PortfolioSyncEvent,
    PortfolioSyncReceipt,
    RelationshipManager,
    Sector,
)
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
from boa_oi.technical.ids import deterministic_uuid
from boa_oi.technical.reference import branch_label

app = create_service_app(
    "customer-service", "SME customer reference data and relationship ownership."
)
PREFIX = "/internal/v1"


def _assignment_table_available(session: Session) -> bool:
    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        return True
    return inspect(bind).has_table(PortfolioAssignment.__tablename__, schema="customer")


def assignment_active_at(assignment: Any, at: datetime) -> Any:
    return and_(
        assignment.valid_from <= at,
        or_(assignment.valid_to.is_(None), assignment.valid_to > at),
    )


def _customer_statement(session: Session) -> tuple[Any, Any, Any]:
    rm = aliased(RelationshipManager)
    if _assignment_table_available(session):
        assignment = aliased(PortfolioAssignment)
        active_assignment = and_(
            Customer.id == assignment.customer_id,
            assignment_active_at(assignment, datetime.now(timezone.utc)),
        )
        if session.get_bind().dialect.name == "sqlite":
            manager_id = func.coalesce(assignment.relationship_manager_id, Customer.rm_id)
            branch_code: Any = func.coalesce(assignment.branch_code, rm.branch_code)
            stmt = (
                select(Customer, rm, branch_code)
                .outerjoin(assignment, active_assignment)
                .join(rm, manager_id == rm.id)
            )
        else:
            branch_code = assignment.branch_code
            stmt = (
                select(Customer, rm, branch_code)
                .join(assignment, active_assignment)
                .join(rm, assignment.relationship_manager_id == rm.id)
            )
        return stmt, rm, branch_code
    stmt = select(Customer, rm, rm.branch_code).join(rm, Customer.rm_id == rm.id)
    return stmt, rm, rm.branch_code


def scoped_customer_statement(
    stmt: Any, rm: Any, principal: Principal, *, branch_code: Any | None = None
) -> Any:
    if {"ADMIN", "SERVICE"} & principal.roles:
        return stmt
    if "RELATIONSHIP_MANAGER" in principal.roles:
        allowed = principal.relationship_manager_ids
        if not allowed:
            raise Problem(
                403, "PORTFOLIO_SCOPE_MISSING", "No relationship-manager scope is assigned."
            )
        stmt = stmt.where(rm.subject_id.in_(allowed))
    elif "BRANCH_MANAGER" in principal.roles:
        allowed = principal.branch_ids
        if not allowed:
            raise Problem(403, "PORTFOLIO_SCOPE_MISSING", "No branch scope is assigned.")
        stmt = stmt.where((branch_code if branch_code is not None else rm.branch_code).in_(allowed))
    return stmt


class CustomerImport(BaseModel):
    customerId: str
    legalName: str
    sector: str
    segment: str
    scenarioCode: str = "NORMAL_CUSTOMER"
    incorporatedOn: date
    status: str = "ACTIVE"
    relationshipManagerId: str
    relationshipManagerName: str | None = None
    branchId: str = "BR-01"
    bankingRelationship: Literal["EXCLUSIVE", "PRIMARY", "SECONDARY", "UNKNOWN"] | None = None
    declaredTurnover: Decimal | None = Field(default=None, gt=0)
    declaredTurnoverAsOf: date | None = None


class BankingRelationshipDeclaration(BaseModel):
    bankingRelationship: Literal["EXCLUSIVE", "PRIMARY", "SECONDARY", "UNKNOWN"]
    reason: str = Field(min_length=8, max_length=1_000)
    declaredTurnover: Decimal | None = Field(default=None, gt=0)
    declaredTurnoverAsOf: date | None = None


class CustomerImportBatch(BaseModel):
    sourceSystem: str = "BANKING_ADAPTER"
    externalBatchId: str
    customers: list[CustomerImport] = Field(max_length=10_000)


class PortfolioAssignmentEvent(BaseModel):
    sourceEventId: str = Field(min_length=1, max_length=120)
    customerId: str = Field(min_length=1, max_length=20)
    portfolioId: str = Field(min_length=1, max_length=80)
    relationshipManagerId: str = Field(min_length=1, max_length=120)
    relationshipManagerName: str | None = Field(default=None, max_length=160)
    branchId: str = Field(min_length=1, max_length=30)
    assignmentType: Literal["PRIMARY"] = "PRIMARY"
    isPrimary: Literal[True] = True
    validFrom: datetime
    validTo: datetime | None = None
    reason: str = Field(min_length=3, max_length=1_000)

    @field_validator("validFrom", "validTo")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Assignment timestamps must include a timezone.")
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def validity_is_ordered(self) -> PortfolioAssignmentEvent:
        if self.validTo is not None and self.validTo <= self.validFrom:
            raise ValueError("validTo must be later than validFrom.")
        return self


class PortfolioSyncBatch(BaseModel):
    contractVersion: Literal["1.0"] = "1.0"
    sourceSystem: str = Field(min_length=1, max_length=40)
    batchRef: str = Field(min_length=1, max_length=120)
    sourceWatermark: str | None = Field(default=None, max_length=120)
    assignments: list[PortfolioAssignmentEvent] = Field(min_length=1, max_length=10_000)


def serialize(
    customer: Customer,
    rm: RelationshipManager | None = None,
    assignment_branch_code: str | None = None,
    flow_visibility: dict[str, Any] | None = None,
    declaration: CustomerBankingDeclaration | None = None,
    turnover_declaration: CustomerBankingDeclaration | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    branch_code = (
        assignment_branch_code
        if assignment_branch_code is not None
        else (rm.branch_code if rm else None)
    )
    relationship = (
        declaration.banking_relationship
        if declaration is not None
        else customer.banking_relationship or "UNKNOWN"
        if as_of is None
        else "UNKNOWN"
    )
    declared_at = (
        declaration.declared_at
        if declaration is not None
        else customer.banking_relationship_declared_at
        if as_of is None
        else None
    )
    declared_by = (
        declaration.declared_by
        if declaration is not None
        else customer.banking_relationship_declared_by
        if as_of is None
        else None
    )
    declaration_reason = (
        declaration.reason
        if declaration is not None
        else customer.banking_relationship_reason
        if as_of is None
        else None
    )
    declaration_source = (
        declaration.source
        if declaration is not None
        else customer.banking_relationship_source
        if as_of is None
        else None
    )
    declared_turnover = (
        turnover_declaration.declared_turnover
        if turnover_declaration is not None
        else customer.declared_turnover
        if as_of is None
        else None
    )
    declared_turnover_as_of = (
        turnover_declaration.declared_turnover_as_of
        if turnover_declaration is not None
        else customer.declared_turnover_as_of
        if as_of is None
        else None
    )
    effective_visibility = dict(flow_visibility or {})
    visibility_as_of = effective_visibility.get("asOf")
    if (
        relationship in {"EXCLUSIVE", "PRIMARY", "SECONDARY"}
        and declared_at is not None
        and (
            visibility_as_of is None
            or date.fromisoformat(str(visibility_as_of)) < declared_at.date()
        )
    ):
        effective_visibility = {
            "level": {"EXCLUSIVE": "HIGH", "PRIMARY": "PARTIAL", "SECONDARY": "LOW"}[relationship],
            "estimatedShare": None,
            "method": "DECLARED",
            "asOf": declared_at.date().isoformat(),
            "evidence": [
                {
                    "fact": "BANKING_RELATIONSHIP_DECLARED",
                    "value": relationship,
                    "observedAt": declared_at.isoformat(),
                }
            ],
            "fingerprintCount90d": 0,
            "fingerprintPrevious90d": 0,
            "fingerprintGrowth90d": 0,
            "categorizationCoverage": 0,
            "status": "PENDING_ANALYTICS_RECOMPUTE",
        }
    return {
        "customerId": customer.customer_ref,
        "legalName": customer.legal_name,
        "tradeName": customer.legal_name,
        "industry": customer.sector_code,
        "sector": customer.sector_code,
        "segment": customer.segment_code,
        "country": "MA",
        "branchId": branch_code,
        "branchName": branch_label(branch_code),
        "relationshipManagerId": rm.subject_id if rm else None,
        "relationshipManagerName": rm.display_name if rm else None,
        "bankingRelationship": relationship,
        "bankingRelationshipDeclaration": (
            {
                "value": relationship,
                "declaredAt": declared_at.isoformat() if declared_at else None,
                "declaredBy": declared_by,
                "reason": declaration_reason,
                "source": declaration_source,
            }
            if declaration_source
            else None
        ),
        "declaredTurnover": float(declared_turnover) if declared_turnover is not None else None,
        "declaredTurnoverAsOf": declared_turnover_as_of.isoformat()
        if declared_turnover_as_of
        else None,
        "flowVisibility": effective_visibility,
        "status": customer.status,
        "incorporatedOn": (
            customer.incorporated_on.isoformat() if customer.incorporated_on else None
        ),
        "createdAt": customer.created_at.isoformat() if customer.created_at else None,
        "updatedAt": customer.updated_at.isoformat() if customer.updated_at else None,
    }


def latest_flow_visibility(
    session: Session, customer: Customer, *, as_of: date | None = None
) -> dict[str, Any]:
    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not inspect(bind).has_table(
        FlowVisibilitySnapshot.__tablename__, schema="analytics"
    ):
        return {
            "level": "UNKNOWN",
            "estimatedShare": None,
            "method": "NONE",
            "asOf": None,
            "evidence": [],
            "fingerprintCount90d": 0,
            "fingerprintPrevious90d": 0,
            "fingerprintGrowth90d": 0,
            "categorizationCoverage": 0,
        }
    stmt = select(FlowVisibilitySnapshot).where(FlowVisibilitySnapshot.customer_id == customer.id)
    if as_of is not None:
        stmt = stmt.where(FlowVisibilitySnapshot.as_of_date <= as_of)
    row = session.scalar(
        stmt.order_by(
            FlowVisibilitySnapshot.as_of_date.desc(),
            FlowVisibilitySnapshot.created_at.desc(),
        ).limit(1)
    )
    if row is None:
        return {
            "level": "UNKNOWN",
            "estimatedShare": None,
            "method": "NONE",
            "asOf": None,
            "evidence": [],
            "fingerprintCount90d": 0,
            "fingerprintPrevious90d": 0,
            "fingerprintGrowth90d": 0,
            "categorizationCoverage": 0,
        }
    return {
        "level": row.level,
        "estimatedShare": float(row.estimated_share) if row.estimated_share is not None else None,
        "method": row.method,
        "asOf": row.as_of_date.isoformat(),
        "evidence": row.evidence_json,
        "fingerprintCount90d": row.fingerprint_count_90d,
        "fingerprintPrevious90d": row.fingerprint_previous_90d,
        "fingerprintGrowth90d": row.fingerprint_count_90d - row.fingerprint_previous_90d,
        "categorizationCoverage": float(row.categorization_coverage),
    }


def latest_banking_declarations(
    session: Session, customer: Customer, *, as_of: date
) -> tuple[CustomerBankingDeclaration | None, CustomerBankingDeclaration | None]:
    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not inspect(bind).has_table(
        CustomerBankingDeclaration.__tablename__, schema="customer"
    ):
        return None, None
    cutoff = datetime.combine(as_of + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    relationship = session.scalar(
        select(CustomerBankingDeclaration)
        .where(
            CustomerBankingDeclaration.customer_id == customer.id,
            CustomerBankingDeclaration.declared_at < cutoff,
        )
        .order_by(CustomerBankingDeclaration.declared_at.desc())
        .limit(1)
    )
    turnover = session.scalar(
        select(CustomerBankingDeclaration)
        .where(
            CustomerBankingDeclaration.customer_id == customer.id,
            CustomerBankingDeclaration.declared_at < cutoff,
            CustomerBankingDeclaration.declared_turnover.is_not(None),
            CustomerBankingDeclaration.declared_turnover_as_of <= as_of,
        )
        .order_by(
            CustomerBankingDeclaration.declared_turnover_as_of.desc(),
            CustomerBankingDeclaration.declared_at.desc(),
        )
        .limit(1)
    )
    return relationship, turnover


@app.get(
    f"{PREFIX}/customers",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Customers"],
)
def list_customers(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    cursor: str | None = None,
    q: str | None = None,
    customer_id: Annotated[str | None, Query(alias="customerId")] = None,
    company_name: Annotated[str | None, Query(alias="companyName")] = None,
    industry: str | None = None,
    sector: str | None = None,
    segment: str | None = None,
    relationship_manager_id: Annotated[str | None, Query(alias="relationshipManagerId")] = None,
    sort: str = "customerId",
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "q",
            "customerId",
            "companyName",
            "industry",
            "sector",
            "segment",
            "relationshipManagerId",
            "sort",
        },
    )
    offset = decode_cursor(cursor)
    stmt, rm, branch_code = _customer_statement(session)
    stmt = scoped_customer_statement(stmt, rm, principal, branch_code=branch_code)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Customer.customer_ref.ilike(pattern),
                Customer.legal_name.ilike(pattern),
                Customer.sector_code.ilike(pattern),
            )
        )
    if customer_id:
        stmt = stmt.where(Customer.customer_ref == customer_id)
    if company_name:
        stmt = stmt.where(Customer.legal_name.ilike(f"%{company_name}%"))
    if industry or sector:
        stmt = stmt.where(Customer.sector_code == (sector or industry))
    if segment:
        if segment.upper() == "SME":
            stmt = stmt.where(Customer.segment_code.in_(("SMALL", "MEDIUM")))
        else:
            stmt = stmt.where(Customer.segment_code == segment)
    if relationship_manager_id:
        stmt = stmt.where(rm.subject_id == relationship_manager_id)
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    columns = {
        "customerId": Customer.customer_ref,
        "legalName": Customer.legal_name,
        "sector": Customer.sector_code,
        "createdAt": Customer.created_at,
    }
    if key not in columns:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported customer sort field.")
    column = columns[key]
    stmt = (
        stmt.order_by(column.desc() if descending else column.asc(), Customer.id)
        .offset(offset)
        .limit(page_size + 1)
    )
    rows = session.execute(stmt).all()
    return page_response(
        request,
        [
            serialize(
                customer,
                manager,
                branch,
                latest_flow_visibility(session, customer),
            )
            for customer, manager, branch in rows
        ],
        page_size=page_size,
        offset=offset,
        total_count=None,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Customers"],
)
def get_customer(
    customer_id: str,
    as_of: Annotated[date | None, Query(alias="asOf")] = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt, rm, branch_code = _customer_statement(session)
    stmt = scoped_customer_statement(
        stmt.where(Customer.customer_ref == customer_id),
        rm,
        principal,
        branch_code=branch_code,
    )
    row = session.execute(stmt).first()
    if row is None:
        raise not_found("Customer")
    customer = row[0]
    relationship_declaration, turnover_declaration = (
        latest_banking_declarations(session, customer, as_of=as_of) if as_of else (None, None)
    )
    return serialize(
        customer,
        row[1],
        row[2],
        latest_flow_visibility(session, customer, as_of=as_of),
        declaration=relationship_declaration,
        turnover_declaration=turnover_declaration,
        as_of=as_of,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/profile",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    include_in_schema=True,
    tags=["Customers"],
)
def get_profile(
    customer_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return get_customer(customer_id, principal=principal, session=session)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/relationship",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Customers"],
)
def get_relationship(
    customer_id: str,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    profile = get_customer(customer_id, principal=principal, session=session)
    return {
        "customerId": customer_id,
        "relationshipManagerId": profile["relationshipManagerId"],
        "relationshipManagerName": profile["relationshipManagerName"],
        "branchId": profile["branchId"],
    }


@app.put(
    f"{PREFIX}/customers/{{customer_id}}/banking-relationship",
    dependencies=[Depends(require_roles("RELATIONSHIP_MANAGER", "BRANCH_MANAGER"))],
    tags=["Customers"],
)
def declare_banking_relationship(
    customer_id: str,
    payload: BankingRelationshipDeclaration,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt, rm, branch_code = _customer_statement(session)
    scoped = scoped_customer_statement(
        stmt.where(Customer.customer_ref == customer_id),
        rm,
        principal,
        branch_code=branch_code,
    )
    row = session.execute(scoped).first()
    if row is None:
        raise Problem(
            403,
            "CUSTOMER_OUTSIDE_PORTFOLIO",
            "La déclaration est réservée au CC du portefeuille ou au responsable de son agence.",
        )
    customer, manager, assigned_branch = row
    before = {
        "bankingRelationship": customer.banking_relationship,
        "declaredTurnover": float(customer.declared_turnover)
        if customer.declared_turnover is not None
        else None,
    }
    now = datetime.now(timezone.utc)
    customer.banking_relationship = payload.bankingRelationship
    customer.banking_relationship_declared_at = now
    customer.banking_relationship_declared_by = principal.username or principal.subject
    customer.banking_relationship_reason = payload.reason
    customer.banking_relationship_source = "RELATIONSHIP_MANAGER"
    if payload.declaredTurnover is not None:
        customer.declared_turnover = payload.declaredTurnover
        customer.declared_turnover_as_of = payload.declaredTurnoverAsOf or now.date()
        customer.declared_turnover_entered_by = principal.username or principal.subject
        customer.declared_turnover_source = "RELATIONSHIP_MANAGER"
    declaration = CustomerBankingDeclaration(
        id=deterministic_uuid(
            "banking-relationship-declaration",
            customer.id,
            principal.subject,
            now.isoformat(),
        ),
        customer_id=customer.id,
        banking_relationship=payload.bankingRelationship,
        declared_at=now,
        declared_by=principal.username or principal.subject,
        reason=payload.reason,
        source="RELATIONSHIP_MANAGER",
        declared_turnover=payload.declaredTurnover,
        declared_turnover_as_of=(
            payload.declaredTurnoverAsOf or now.date()
            if payload.declaredTurnover is not None
            else None
        ),
        declared_turnover_source=(
            "RELATIONSHIP_MANAGER" if payload.declaredTurnover is not None else None
        ),
    )
    session.add(declaration)
    after = {
        "bankingRelationship": customer.banking_relationship,
        "declaredTurnover": float(customer.declared_turnover)
        if customer.declared_turnover is not None
        else None,
    }
    session.add(
        AuditLog(
            id=deterministic_uuid(
                "banking-relationship-audit",
                customer.customer_ref,
                principal.subject,
                now.isoformat(),
            ),
            occurred_at=now,
            actor_subject_id=principal.subject,
            service_name="customer-service",
            action="BANKING_RELATIONSHIP_DECLARED",
            resource_type="CUSTOMER",
            resource_id=customer.customer_ref,
            correlation_id=correlation_id(request),
            result="SUCCESS",
            metadata_json={"before": before, "after": after, "reason": payload.reason},
        )
    )
    session.commit()
    return serialize(
        customer,
        manager,
        assigned_branch,
        latest_flow_visibility(session, customer),
        declaration,
    )


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def serialize_assignment(
    assignment: PortfolioAssignment,
    manager: RelationshipManager | None = None,
) -> dict[str, Any]:
    return {
        "assignmentId": str(assignment.id),
        "customerId": assignment.customer_id.hex,
        "portfolioId": assignment.portfolio_id,
        "relationshipManagerId": manager.subject_id if manager else None,
        "branchId": assignment.branch_code,
        "assignmentType": assignment.assignment_type,
        "isPrimary": assignment.is_primary,
        "validFrom": assignment.valid_from.isoformat(),
        "validTo": assignment.valid_to.isoformat() if assignment.valid_to else None,
        "sourceSystem": assignment.source_system,
        "sourceEventId": assignment.source_event_id,
        "sourceWatermark": assignment.source_watermark,
        "actor": assignment.actor,
        "reason": assignment.reason,
    }


def _claim_sync_key(
    session: Session,
    namespace: str,
    key: str,
    *,
    code: str,
    message: str,
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    claimed = session.scalar(
        select(
            func.pg_try_advisory_xact_lock(
                func.hashtext(namespace),
                func.hashtext(key),
            )
        )
    )
    if not claimed:
        raise Problem(409, code, message)


def portfolio_sync_principal(
    principal: Principal = Depends(current_principal),
) -> Principal:
    if "ADMIN" in principal.roles:
        return principal
    if "SERVICE" in principal.roles and principal.client_id == "banking-integration-service":
        return principal
    raise Problem(
        403,
        "FORBIDDEN",
        "Portfolio synchronization is restricted to administrators and the banking "
        "integration service.",
    )


@app.get(
    f"{PREFIX}/portfolio-assignments",
    tags=["Portfolio synchronization"],
)
def list_portfolio_assignments(
    request: Request,
    customer_id: Annotated[str, Query(alias="customerId", min_length=1)],
    as_of: Annotated[datetime | None, Query(alias="asOf")] = None,
    _principal: Principal = Depends(portfolio_sync_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"customerId", "asOf"})
    customer = session.scalar(select(Customer).where(Customer.customer_ref == customer_id))
    if customer is None:
        raise not_found("Customer")
    stmt = (
        select(PortfolioAssignment, RelationshipManager)
        .join(
            RelationshipManager,
            PortfolioAssignment.relationship_manager_id == RelationshipManager.id,
        )
        .where(PortfolioAssignment.customer_id == customer.id)
    )
    if as_of is not None:
        at = _utc(as_of)
        stmt = stmt.where(assignment_active_at(PortfolioAssignment, at))
    rows = session.execute(stmt.order_by(PortfolioAssignment.valid_from)).all()
    data = []
    for assignment, manager in rows:
        item = serialize_assignment(assignment, manager)
        item["customerId"] = customer.customer_ref
        data.append(item)
    return {
        "data": data,
        "meta": {"customerId": customer_id, "asOf": _utc(as_of).isoformat() if as_of else None},
    }


@app.post(
    f"{PREFIX}/portfolio-assignments/sync",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Portfolio synchronization"],
)
def sync_portfolio_assignments(
    batch: PortfolioSyncBatch,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    principal: Principal = Depends(portfolio_sync_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    request_payload = batch.model_dump(mode="json")
    request_hash = canonical_hash(request_payload)
    _claim_sync_key(
        session,
        f"portfolio-sync-batch:{batch.sourceSystem}",
        batch.batchRef,
        code="PORTFOLIO_SYNC_IN_PROGRESS",
        message="This source batch is already being synchronized.",
    )
    existing_receipt = session.scalar(
        select(PortfolioSyncReceipt).where(
            or_(
                PortfolioSyncReceipt.idempotency_key == idempotency_key,
                and_(
                    PortfolioSyncReceipt.source_system == batch.sourceSystem,
                    PortfolioSyncReceipt.batch_ref == batch.batchRef,
                ),
            )
        )
    )
    if existing_receipt is not None:
        if existing_receipt.request_hash != request_hash:
            raise Problem(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key or source batch was reused with different content.",
            )
        return {**existing_receipt.response_json, "replayed": True}

    applied = 0
    unchanged = 0
    replayed_events = 0
    event_results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    corr = correlation_id(request)
    for event in sorted(batch.assignments, key=lambda item: (item.validFrom, item.sourceEventId)):
        _claim_sync_key(
            session,
            f"portfolio-sync-event:{batch.sourceSystem}",
            event.sourceEventId,
            code="SOURCE_EVENT_IN_PROGRESS",
            message=f"Source event {event.sourceEventId} is already being processed.",
        )
        _claim_sync_key(
            session,
            "portfolio-sync-customer",
            event.customerId,
            code="CUSTOMER_ASSIGNMENT_IN_PROGRESS",
            message=f"Customer {event.customerId} is already being reassigned.",
        )
        event_payload = event.model_dump(mode="json")
        event_hash = canonical_hash(event_payload)
        previous_event = session.scalar(
            select(PortfolioSyncEvent).where(
                PortfolioSyncEvent.source_system == batch.sourceSystem,
                PortfolioSyncEvent.source_event_id == event.sourceEventId,
            )
        )
        if previous_event is not None:
            if previous_event.payload_hash != event_hash:
                raise Problem(
                    409,
                    "SOURCE_EVENT_REUSED",
                    f"Source event {event.sourceEventId} was reused with different content.",
                )
            replayed_events += 1
            event_results.append(
                {
                    "sourceEventId": event.sourceEventId,
                    "status": "REPLAYED",
                    "assignmentId": (
                        str(previous_event.assignment_id)
                        if previous_event.assignment_id is not None
                        else None
                    ),
                }
            )
            continue

        customer = session.scalar(select(Customer).where(Customer.customer_ref == event.customerId))
        if customer is None:
            raise Problem(422, "CUSTOMER_NOT_FOUND", f"Unknown customer: {event.customerId}.")
        if event.validTo is not None and _utc(event.validTo) <= now:
            raise Problem(
                409,
                "HISTORICAL_RECONCILIATION_REQUIRED",
                "An assignment that already ended requires the historical reconciliation process.",
            )
        manager = session.scalar(
            select(RelationshipManager).where(
                RelationshipManager.subject_id == event.relationshipManagerId
            )
        )
        if manager is None:
            manager = RelationshipManager(
                id=deterministic_uuid("rm", event.relationshipManagerId),
                subject_id=event.relationshipManagerId,
                display_name=event.relationshipManagerName or event.relationshipManagerId,
                branch_code=event.branchId,
                active=True,
                created_by=principal.subject,
            )
            session.add(manager)
            session.flush()
        else:
            if manager.branch_code != event.branchId:
                raise Problem(
                    409,
                    "RELATIONSHIP_MANAGER_BRANCH_CONFLICT",
                    "The relationship manager belongs to another branch in the master data.",
                )

        effective_at = _utc(event.validFrom)
        latest = session.scalar(
            select(PortfolioAssignment)
            .where(PortfolioAssignment.customer_id == customer.id)
            .order_by(PortfolioAssignment.valid_from.desc())
            .limit(1)
        )
        if latest is not None and effective_at < _utc(latest.valid_from):
            raise Problem(
                409,
                "OUT_OF_ORDER_ASSIGNMENT",
                "Backdated assignment events require an explicit reconciliation process.",
            )
        current = session.scalar(
            select(PortfolioAssignment).where(
                PortfolioAssignment.customer_id == customer.id,
                PortfolioAssignment.valid_from <= effective_at,
                or_(
                    PortfolioAssignment.valid_to.is_(None),
                    PortfolioAssignment.valid_to > effective_at,
                ),
            )
        )
        before = serialize_assignment(current) if current is not None else None
        same_target = current is not None and (
            current.relationship_manager_id == manager.id
            and current.branch_code == event.branchId
            and current.portfolio_id == event.portfolioId
            and current.assignment_type == event.assignmentType
            and current.is_primary == event.isPrimary
        )
        assignment = current
        event_status = "NO_CHANGE"
        if same_target:
            assert current is not None
            requested_valid_to = _utc(event.validTo) if event.validTo else None
            current_valid_to = _utc(current.valid_to) if current.valid_to else None
            if effective_at == _utc(current.valid_from) and requested_valid_to == current_valid_to:
                unchanged += 1
            else:
                raise Problem(
                    409,
                    "ASSIGNMENT_INTERVAL_CONFLICT",
                    "An existing interval can only be replayed with identical bounds.",
                )
        else:
            if current is not None:
                if effective_at <= _utc(current.valid_from):
                    raise Problem(
                        409,
                        "ASSIGNMENT_INTERVAL_CONFLICT",
                        "The effective timestamp conflicts with the current assignment.",
                    )
                current.valid_to = effective_at
            assignment_id = deterministic_uuid(
                "portfolio-assignment",
                batch.sourceSystem,
                event.sourceEventId,
            )
            assignment = PortfolioAssignment(
                id=assignment_id,
                customer_id=customer.id,
                relationship_manager_id=manager.id,
                branch_code=event.branchId,
                portfolio_id=event.portfolioId,
                assignment_type=event.assignmentType,
                is_primary=event.isPrimary,
                valid_from=effective_at,
                valid_to=_utc(event.validTo) if event.validTo else None,
                source_system=batch.sourceSystem,
                source_event_id=event.sourceEventId,
                source_payload_hash=event_hash,
                source_watermark=batch.sourceWatermark,
                actor=principal.subject,
                reason=event.reason,
            )
            session.add(assignment)
            if effective_at <= now and (event.validTo is None or _utc(event.validTo) > now):
                customer.rm_id = manager.id
            applied += 1
            event_status = "APPLIED"

        resolved_assignment_id = assignment.id if assignment is not None else None
        after = serialize_assignment(assignment, manager) if assignment is not None else None
        session.add(
            PortfolioSyncEvent(
                id=deterministic_uuid(
                    "portfolio-sync-event", batch.sourceSystem, event.sourceEventId
                ),
                source_system=batch.sourceSystem,
                source_event_id=event.sourceEventId,
                batch_ref=batch.batchRef,
                payload_hash=event_hash,
                customer_ref=event.customerId,
                status=event_status,
                assignment_id=resolved_assignment_id,
                correlation_id=corr,
                occurred_at=now,
            )
        )
        session.add(
            AuditLog(
                id=deterministic_uuid("audit", batch.sourceSystem, event.sourceEventId),
                actor_subject_id=principal.subject,
                service_name="customer-service",
                action=f"PORTFOLIO_ASSIGNMENT_{event_status}",
                resource_type="PORTFOLIO_ASSIGNMENT",
                resource_id=event.customerId,
                correlation_id=corr,
                result="SUCCESS",
                metadata_json={
                    "before": before,
                    "after": after,
                    "sourceSystem": batch.sourceSystem,
                    "sourceEventId": event.sourceEventId,
                    "batchRef": batch.batchRef,
                    "sourceWatermark": batch.sourceWatermark,
                    "payloadHash": event_hash,
                },
            )
        )
        if event_status == "APPLIED" and assignment is not None:
            session.add(
                OutboxMessage(
                    id=deterministic_uuid("outbox", batch.sourceSystem, event.sourceEventId),
                    event_type="PORTFOLIO_ASSIGNMENT_CHANGED",
                    aggregate_type="CUSTOMER",
                    aggregate_id=event.customerId,
                    payload_json={
                        "customerId": event.customerId,
                        "assignmentId": str(assignment.id),
                        "portfolioId": event.portfolioId,
                        "relationshipManagerId": event.relationshipManagerId,
                        "branchId": event.branchId,
                        "validFrom": effective_at.isoformat(),
                        "validTo": event.validTo.isoformat() if event.validTo else None,
                        "sourceSystem": batch.sourceSystem,
                        "sourceEventId": event.sourceEventId,
                    },
                    correlation_id=corr,
                    causation_id=event.sourceEventId,
                    occurred_at=now,
                )
            )
        event_results.append(
            {
                "sourceEventId": event.sourceEventId,
                "status": event_status,
                "assignmentId": (str(resolved_assignment_id) if resolved_assignment_id else None),
            }
        )

    receipt_id = deterministic_uuid("portfolio-sync", batch.sourceSystem, batch.batchRef)
    response = {
        "jobId": str(receipt_id),
        "status": "COMPLETED",
        "sourceSystem": batch.sourceSystem,
        "batchRef": batch.batchRef,
        "sourceWatermark": batch.sourceWatermark,
        "received": len(batch.assignments),
        "applied": applied,
        "unchanged": unchanged,
        "replayedEvents": replayed_events,
        "events": event_results,
        "replayed": False,
    }
    session.add(
        PortfolioSyncReceipt(
            id=receipt_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            source_system=batch.sourceSystem,
            batch_ref=batch.batchRef,
            source_watermark=batch.sourceWatermark,
            row_count=len(batch.assignments),
            status="COMPLETED",
            response_json=response,
            correlation_id=corr,
            created_at=now,
            completed_at=now,
        )
    )
    session.commit()
    return response


@app.post(
    f"{PREFIX}/imports/customers",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def import_customers(
    batch: CustomerImportBatch,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    request_hash = hashlib.sha256(batch.model_dump_json().encode()).hexdigest()
    existing = session.scalar(
        select(CustomerImportReceipt).where(
            CustomerImportReceipt.idempotency_key == idempotency_key
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise Problem(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was reused with different content.",
            )
        return {
            "jobId": str(existing.id),
            "status": existing.status,
            "imported": existing.row_count,
        }
    imported = 0
    assignment_table_available = _assignment_table_available(session)
    for item in batch.customers:
        imported_at = datetime.now(timezone.utc)
        rm_id = deterministic_uuid("rm", item.relationshipManagerId)
        customer_uuid = deterministic_uuid("customer", item.customerId)
        session.execute(
            pg_insert(RelationshipManager)
            .values(
                id=rm_id,
                subject_id=item.relationshipManagerId,
                display_name=item.relationshipManagerName or item.relationshipManagerId,
                branch_code=item.branchId,
                active=True,
                created_by="banking-integration",
            )
            .on_conflict_do_nothing(index_elements=[RelationshipManager.subject_id])
        )
        session.execute(
            pg_insert(Sector)
            .values(
                id=deterministic_uuid("sector", item.sector),
                code=item.sector,
                label=item.sector.replace("_", " ").title(),
                active=True,
            )
            .on_conflict_do_nothing(index_elements=[Sector.code])
        )
        customer_insert = pg_insert(Customer).values(
            id=customer_uuid,
            customer_ref=item.customerId,
            legal_name=item.legalName,
            sector_code=item.sector,
            segment_code=item.segment,
            scenario_code=item.scenarioCode,
            incorporated_on=item.incorporatedOn,
            status=item.status,
            rm_id=rm_id,
            banking_relationship=item.bankingRelationship,
            banking_relationship_declared_at=(
                imported_at if item.bankingRelationship is not None else None
            ),
            banking_relationship_declared_by=(
                batch.sourceSystem if item.bankingRelationship is not None else None
            ),
            banking_relationship_reason=(
                f"Import SI {batch.sourceSystem} / lot {batch.externalBatchId}"
                if item.bankingRelationship is not None
                else None
            ),
            banking_relationship_source=(
                "INFORMATION_SYSTEM" if item.bankingRelationship is not None else None
            ),
            declared_turnover=item.declaredTurnover,
            declared_turnover_as_of=item.declaredTurnoverAsOf,
            declared_turnover_entered_by=(
                batch.sourceSystem if item.declaredTurnover is not None else None
            ),
            declared_turnover_source=(
                "INFORMATION_SYSTEM" if item.declaredTurnover is not None else None
            ),
            created_by="banking-integration",
        )
        session.execute(
            customer_insert.on_conflict_do_update(
                index_elements=[Customer.customer_ref],
                set_={
                    "legal_name": item.legalName,
                    "sector_code": item.sector,
                    "segment_code": item.segment,
                    "status": item.status,
                    "rm_id": rm_id,
                    "banking_relationship": case(
                        (
                            Customer.banking_relationship_source == "RELATIONSHIP_MANAGER",
                            Customer.banking_relationship,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.banking_relationship,
                            Customer.banking_relationship,
                        ),
                    ),
                    "banking_relationship_declared_at": case(
                        (
                            Customer.banking_relationship_source == "RELATIONSHIP_MANAGER",
                            Customer.banking_relationship_declared_at,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.banking_relationship_declared_at,
                            Customer.banking_relationship_declared_at,
                        ),
                    ),
                    "banking_relationship_declared_by": case(
                        (
                            Customer.banking_relationship_source == "RELATIONSHIP_MANAGER",
                            Customer.banking_relationship_declared_by,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.banking_relationship_declared_by,
                            Customer.banking_relationship_declared_by,
                        ),
                    ),
                    "banking_relationship_reason": case(
                        (
                            Customer.banking_relationship_source == "RELATIONSHIP_MANAGER",
                            Customer.banking_relationship_reason,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.banking_relationship_reason,
                            Customer.banking_relationship_reason,
                        ),
                    ),
                    "banking_relationship_source": case(
                        (
                            Customer.banking_relationship_source == "RELATIONSHIP_MANAGER",
                            Customer.banking_relationship_source,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.banking_relationship_source,
                            Customer.banking_relationship_source,
                        ),
                    ),
                    "declared_turnover": case(
                        (
                            Customer.declared_turnover_source == "RELATIONSHIP_MANAGER",
                            Customer.declared_turnover,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.declared_turnover,
                            Customer.declared_turnover,
                        ),
                    ),
                    "declared_turnover_as_of": case(
                        (
                            Customer.declared_turnover_source == "RELATIONSHIP_MANAGER",
                            Customer.declared_turnover_as_of,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.declared_turnover_as_of,
                            Customer.declared_turnover_as_of,
                        ),
                    ),
                    "declared_turnover_entered_by": case(
                        (
                            Customer.declared_turnover_source == "RELATIONSHIP_MANAGER",
                            Customer.declared_turnover_entered_by,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.declared_turnover_entered_by,
                            Customer.declared_turnover_entered_by,
                        ),
                    ),
                    "declared_turnover_source": case(
                        (
                            Customer.declared_turnover_source == "RELATIONSHIP_MANAGER",
                            Customer.declared_turnover_source,
                        ),
                        else_=func.coalesce(
                            customer_insert.excluded.declared_turnover_source,
                            Customer.declared_turnover_source,
                        ),
                    ),
                },
            )
        )
        if assignment_table_available:
            assignment_time = datetime.now(timezone.utc)
            scheduled_assignment = session.scalar(
                select(PortfolioAssignment.id).where(
                    PortfolioAssignment.customer_id == customer_uuid,
                    PortfolioAssignment.valid_from > assignment_time,
                )
            )
            if scheduled_assignment is not None:
                raise Problem(
                    409,
                    "SCHEDULED_ASSIGNMENT_EXISTS",
                    "Use the governed portfolio synchronization endpoint when a future "
                    "assignment exists.",
                )
            current_assignment = session.scalar(
                select(PortfolioAssignment).where(
                    PortfolioAssignment.customer_id == customer_uuid,
                    PortfolioAssignment.valid_from <= assignment_time,
                    or_(
                        PortfolioAssignment.valid_to.is_(None),
                        PortfolioAssignment.valid_to > assignment_time,
                    ),
                )
            )
            if current_assignment is not None and (
                current_assignment.relationship_manager_id != rm_id
                or current_assignment.branch_code != item.branchId
            ):
                if current_assignment.valid_from >= assignment_time:
                    assignment_time = current_assignment.valid_from + timedelta(microseconds=1)
                session.execute(
                    update(PortfolioAssignment)
                    .where(PortfolioAssignment.id == current_assignment.id)
                    .values(valid_to=assignment_time)
                )
                current_assignment = None
            if current_assignment is None:
                session.add(
                    PortfolioAssignment(
                        id=deterministic_uuid(
                            "portfolio-assignment", customer_uuid, assignment_time.isoformat()
                        ),
                        customer_id=customer_uuid,
                        relationship_manager_id=rm_id,
                        branch_code=item.branchId,
                        portfolio_id=f"PORTFOLIO-{item.branchId}",
                        assignment_type="PRIMARY",
                        is_primary=True,
                        valid_from=assignment_time,
                        valid_to=None,
                        source_system=batch.sourceSystem,
                        source_event_id=f"{batch.externalBatchId}:{item.customerId}",
                        source_payload_hash=canonical_hash(item.model_dump(mode="json")),
                        source_watermark=batch.externalBatchId,
                        actor=batch.sourceSystem,
                        reason=f"Customer import {batch.externalBatchId}",
                    )
                )
        imported += 1
    record = CustomerImportReceipt(
        id=deterministic_uuid("import", "CUSTOMERS", idempotency_key),
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        row_count=imported,
        status="COMPLETED",
        correlation_id=correlation_id(request),
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    return {"jobId": str(record.id), "status": "COMPLETED", "imported": imported}


__all__ = ["app", "serialize"]
