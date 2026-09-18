from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from boa_oi.models.entities import (
    Customer,
    CustomerImportReceipt,
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

app = create_service_app(
    "customer-service", "SME customer reference data and relationship ownership."
)
PREFIX = "/internal/v1"


def scoped_customer_statement(stmt: Any, rm: Any, principal: Principal) -> Any:
    if {"ADMIN", "SERVICE"} & principal.roles:
        return stmt
    if "RELATIONSHIP_MANAGER" in principal.roles:
        allowed = principal.relationship_manager_ids
        if not allowed:
            raise Problem(403, "PORTFOLIO_SCOPE_MISSING", "No relationship-manager scope is assigned.")
        stmt = stmt.where(rm.subject_id.in_(allowed))
    elif "BRANCH_MANAGER" in principal.roles:
        allowed = principal.branch_ids
        if not allowed:
            raise Problem(403, "PORTFOLIO_SCOPE_MISSING", "No branch scope is assigned.")
        stmt = stmt.where(rm.branch_code.in_(allowed))
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


def serialize(customer: Customer, rm: RelationshipManager | None = None) -> dict[str, Any]:
    return {
        "customerId": customer.customer_ref,
        "legalName": customer.legal_name,
        "tradeName": customer.legal_name,
        "industry": customer.sector_code,
        "sector": customer.sector_code,
        "segment": customer.segment_code,
        "country": "MA",
        "branchId": rm.branch_code if rm else None,
        "relationshipManagerId": rm.subject_id if rm else None,
        "relationshipManagerName": rm.display_name if rm else None,
        "status": customer.status,
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
    rm = aliased(RelationshipManager)
    stmt = select(Customer, rm).join(rm, Customer.rm_id == rm.id)
    stmt = scoped_customer_statement(stmt, rm, principal)
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
        [serialize(customer, manager) for customer, manager in rows],
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
    stmt = scoped_customer_statement(
        select(Customer, RelationshipManager)
        .join(RelationshipManager, Customer.rm_id == RelationshipManager.id)
        .where(Customer.customer_ref == customer_id),
        RelationshipManager,
        principal,
    )
    row = session.execute(stmt).first()
    if row is None:
        raise not_found("Customer")
    return serialize(row[0], row[1])


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
    for item in batch.customers:
        rm_id = deterministic_uuid("rm", item.relationshipManagerId)
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
                id=deterministic_uuid("customer", item.customerId),
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
