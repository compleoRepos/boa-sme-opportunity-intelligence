from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, inspect, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from boa_oi.models.entities import (
    Customer,
    CustomerImportReceipt,
    PortfolioAssignment,
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


def _customer_statement(session: Session) -> tuple[Any, Any, Any]:
    rm = aliased(RelationshipManager)
    if _assignment_table_available(session):
        assignment = aliased(PortfolioAssignment)
        active_assignment = and_(
            Customer.id == assignment.customer_id,
            assignment.valid_from <= datetime.now(timezone.utc),
            assignment.valid_to.is_(None),
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


class CustomerImportBatch(BaseModel):
    sourceSystem: str = "BANKING_ADAPTER"
    externalBatchId: str
    customers: list[CustomerImport] = Field(max_length=10_000)


def serialize(
    customer: Customer,
    rm: RelationshipManager | None = None,
    assignment_branch_code: str | None = None,
) -> dict[str, Any]:
    branch_code = (
        assignment_branch_code
        if assignment_branch_code is not None
        else (rm.branch_code if rm else None)
    )
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
        "status": customer.status,
        "incorporatedOn": (
            customer.incorporated_on.isoformat() if customer.incorporated_on else None
        ),
        "createdAt": customer.created_at.isoformat() if customer.created_at else None,
        "updatedAt": customer.updated_at.isoformat() if customer.updated_at else None,
    }


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
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = (
        stmt.order_by(column.desc() if descending else column.asc(), Customer.id)
        .offset(offset)
        .limit(page_size + 1)
    )
    rows = session.execute(stmt).all()
    return page_response(
        request,
        [serialize(customer, manager, branch) for customer, manager, branch in rows],
        page_size=page_size,
        offset=offset,
        total_count=total,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Customers"],
)
def get_customer(
    customer_id: str,
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
    return serialize(row[0], row[1], row[2])


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
    return get_customer(customer_id, principal, session)


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
    profile = get_customer(customer_id, principal, session)
    return {
        "customerId": customer_id,
        "relationshipManagerId": profile["relationshipManagerId"],
        "relationshipManagerName": profile["relationshipManagerName"],
        "branchId": profile["branchId"],
    }


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
        session.execute(
            pg_insert(Customer)
            .values(
                id=customer_uuid,
                customer_ref=item.customerId,
                legal_name=item.legalName,
                sector_code=item.sector,
                segment_code=item.segment,
                scenario_code=item.scenarioCode,
                incorporated_on=item.incorporatedOn,
                status=item.status,
                rm_id=rm_id,
                created_by="banking-integration",
            )
            .on_conflict_do_update(
                index_elements=[Customer.customer_ref],
                set_={
                    "legal_name": item.legalName,
                    "sector_code": item.sector,
                    "segment_code": item.segment,
                    "status": item.status,
                    "rm_id": rm_id,
                },
            )
        )
        if assignment_table_available:
            current_assignment = session.scalar(
                select(PortfolioAssignment).where(
                    PortfolioAssignment.customer_id == customer_uuid,
                    PortfolioAssignment.valid_to.is_(None),
                )
            )
            assignment_time = datetime.now(timezone.utc)
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
                        valid_from=assignment_time,
                        valid_to=None,
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
