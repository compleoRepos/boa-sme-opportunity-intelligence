from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.catalog import PRODUCTS_BY_CODE
from boa_oi.http_clients import service_request
from boa_oi.models.entities import CustomerProduct, Product, ProductImportReceipt
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

app = create_service_app("product-service", "Product catalog, product ownership and product gaps.")
PREFIX = "/internal/v1"


def customer_url() -> str:
    value = os.getenv("CUSTOMER_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            "CUSTOMER_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


async def assert_customer_scope(request: Request, principal: Principal, customer_id: str) -> None:
    if {"ADMIN", "SERVICE", "DATA_ANALYST"} & principal.roles:
        return
    await service_request(
        "GET",
        f"{customer_url()}/internal/v1/customers/{customer_id}",
        correlation_id=correlation_id(request),
        incoming_authorization=request.headers.get("Authorization"),
        dev_principal=request.headers.get("X-Dev-Principal"),
    )


def validate_governed_product(product: "ProductIn") -> None:
    expected = PRODUCTS_BY_CODE.get(product.productId)
    if expected is None:
        raise Problem(
            422,
            "UNKNOWN_CATALOG_PRODUCT",
            f"Product {product.productId} is not part of the governed pilot catalogue.",
        )
    mismatches: list[str] = []
    if product.family != expected.family:
        mismatches.append("family")
    if product.sourceUrl != expected.source_url:
        mismatches.append("sourceUrl")
    if mismatches:
        raise Problem(
            422,
            "CATALOG_PRODUCT_MISMATCH",
            f"Product {product.productId} differs from the governed catalogue: "
            + ", ".join(mismatches),
        )


def validate_governed_ownerships(batch: "ProductBatch", session: Session) -> None:
    ownership_codes = {item.productId for item in batch.ownerships}
    unknown_codes = sorted(ownership_codes - PRODUCTS_BY_CODE.keys())
    if unknown_codes:
        raise Problem(
            422,
            "UNKNOWN_CATALOG_PRODUCT",
            "Ownerships reference products outside the governed pilot catalogue: "
            + ", ".join(unknown_codes),
        )
    batch_availability = {item.productId: item.active for item in batch.products}
    database_availability: dict[str, bool] = {
        str(code): bool(active)
        for code, active in session.execute(
            select(Product.product_code, Product.active).where(
                Product.product_code.in_(ownership_codes)
            )
        )
    }
    unavailable_codes = sorted(
        code
        for code in ownership_codes
        if not batch_availability.get(code, database_availability.get(code, False))
    )
    if unavailable_codes:
        raise Problem(
            422,
            "OWNERSHIP_PRODUCT_UNAVAILABLE",
            "Ownerships reference governed products that are absent or inactive: "
            + ", ".join(unavailable_codes),
        )


class ProductIn(BaseModel):
    productId: str
    name: str
    category: str
    family: str = "UNCLASSIFIED"
    description: str = ""
    sourceUrl: str | None = None
    eligibilityRules: dict[str, Any] = Field(default_factory=dict)
    targetSegment: list[str] = Field(default_factory=list)
    currency: list[str] = Field(default_factory=lambda: ["MAD"])
    active: bool = True


class OwnershipIn(BaseModel):
    customerId: str
    productId: str
    status: str = "ACTIVE"
    openedOn: date
    utilizationRatio: Decimal | None = None


class ProductBatch(BaseModel):
    externalBatchId: str
    products: list[ProductIn] = Field(max_length=1_000)
    ownerships: list[OwnershipIn] = Field(default_factory=list, max_length=100_000)


def assert_catalog_ready(engine: Any) -> None:
    with Session(engine) as session:
        rows = session.execute(
            select(
                Product.product_code,
                Product.family,
                Product.source_url,
                Product.active,
            )
        ).all()
    observed = {
        str(code): {"family": family, "sourceUrl": source_url, "active": bool(active)}
        for code, family, source_url, active in rows
    }
    issues: list[str] = []
    for code, expected in PRODUCTS_BY_CODE.items():
        current = observed.get(code)
        if current is None:
            issues.append(f"{code}:missing")
        elif not current["active"]:
            issues.append(f"{code}:inactive")
        elif current["family"] != expected.family or current["sourceUrl"] != expected.source_url:
            issues.append(f"{code}:metadata")
    unexpected_active = sorted(
        code
        for code, current in observed.items()
        if current["active"] and code not in PRODUCTS_BY_CODE
    )
    issues.extend(f"{code}:ungoverned" for code in unexpected_active)
    if issues:
        raise Problem(
            503,
            "PRODUCT_CATALOG_NOT_READY",
            "The governed pilot catalogue is incomplete or inconsistent: " + ", ".join(issues),
        )


app.state.readiness_check = assert_catalog_ready


def serialize(product: Product) -> dict[str, Any]:
    return {
        "productId": product.product_code,
        "name": product.name,
        "category": product.category,
        "family": product.family or product.product_code,
        "description": product.description,
        "sourceUrl": product.source_url,
        "eligibilityRules": product.eligibility_rules_json,
        "targetSegment": product.target_segments_json,
        "currency": product.currencies_json,
        "active": product.active,
    }


@app.get(
    f"{PREFIX}/products",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Products"],
)
def list_products(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    cursor: str | None = None,
    category: str | None = None,
    family: str | None = None,
    target_segment: Annotated[str | None, Query(alias="targetSegment")] = None,
    currency: str | None = None,
    active: bool | None = True,
    sort: str = "name",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "category",
            "family",
            "targetSegment",
            "currency",
            "active",
            "sort",
            "q",
        },
    )
    offset = decode_cursor(cursor)
    stmt = select(Product)
    if category:
        stmt = stmt.where(Product.category == category)
    if family:
        stmt = stmt.where(Product.family == family)
    if target_segment:
        stmt = stmt.where(Product.target_segments_json.contains([target_segment]))
    if currency:
        stmt = stmt.where(Product.currencies_json.contains([currency]))
    if active is not None:
        stmt = stmt.where(Product.active == active)
    if request.query_params.get("q"):
        stmt = stmt.where(Product.name.ilike(f"%{request.query_params['q']}%"))
    column = {
        "name": Product.name,
        "category": Product.category,
        "family": Product.family,
        "productId": Product.product_code,
    }.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported product sort field.")
    rows = list(
        session.scalars(
            stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), Product.id)
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
    f"{PREFIX}/products/{{product_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Products"],
)
def get_product(product_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    product = session.scalar(select(Product).where(Product.product_code == product_id))
    if product is None:
        raise not_found("Product")
    return serialize(product)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/products",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Products"],
)
async def customer_products(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 100,
    cursor: str | None = None,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await assert_customer_scope(request, principal, customer_id)
    reject_unknown_filters(request, {"pageSize", "cursor", "sort"})
    offset = decode_cursor(cursor)
    rows = session.execute(
        select(Product, CustomerProduct)
        .join(CustomerProduct, CustomerProduct.product_id == Product.id)
        .where(
            CustomerProduct.customer_id == deterministic_uuid("customer", customer_id),
            CustomerProduct.status == "ACTIVE",
        )
        .order_by(Product.name)
        .offset(offset)
        .limit(page_size + 1)
    ).all()
    data = [
        {
            **serialize(product),
            "ownershipStatus": owned.status,
            "utilizationRatio": float(owned.utilization_ratio)
            if owned.utilization_ratio is not None
            else None,
        }
        for product, owned in rows
    ]
    return page_response(request, data, page_size=page_size, offset=offset, total_count=None)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/product-gaps",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Products"],
)
async def product_gaps(
    customer_id: str,
    request: Request,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    await assert_customer_scope(request, principal, customer_id)
    products = list(session.scalars(select(Product).where(Product.active.is_(True))))
    owned_rows = session.execute(
        select(Product.product_code, CustomerProduct.utilization_ratio)
        .join(CustomerProduct, CustomerProduct.product_id == Product.id)
        .where(
            CustomerProduct.customer_id == deterministic_uuid("customer", customer_id),
            CustomerProduct.status == "ACTIVE",
        )
    ).all()
    owned: dict[str, Decimal | None] = {str(row[0]): row[1] for row in owned_rows}
    gaps = []
    for product in products:
        utilization = owned.get(product.product_code)
        status_value = (
            "ABSENT"
            if product.product_code not in owned
            else (
                "UNDERUTILIZED"
                if utilization is not None and utilization < Decimal("0.20")
                else "OWNED"
            )
        )
        gaps.append(
            {
                "product": serialize(product),
                "status": status_value,
                "isGap": status_value in {"ABSENT", "UNDERUTILIZED"},
            }
        )
    return {"customerId": customer_id, "gaps": gaps}


@app.post(
    f"{PREFIX}/imports/products",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def import_products(
    batch: ProductBatch,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    for product_item in batch.products:
        validate_governed_product(product_item)
    validate_governed_ownerships(batch, session)
    body_hash = hashlib.sha256(batch.model_dump_json().encode()).hexdigest()
    existing = session.scalar(
        select(ProductImportReceipt).where(ProductImportReceipt.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.request_hash != body_hash:
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
    for product_item in batch.products:
        session.execute(
            pg_insert(Product)
            .values(
                id=deterministic_uuid("product", product_item.productId),
                product_code=product_item.productId,
                name=product_item.name,
                category=product_item.category,
                family=product_item.family,
                description=product_item.description,
                source_url=product_item.sourceUrl,
                eligibility_rules_json=product_item.eligibilityRules,
                target_segments_json=product_item.targetSegment,
                currencies_json=product_item.currency,
                active=product_item.active,
                created_by="banking-integration",
            )
            .on_conflict_do_update(
                index_elements=[Product.product_code],
                set_={
                    "name": product_item.name,
                    "category": product_item.category,
                    "family": product_item.family,
                    "description": product_item.description,
                    "source_url": product_item.sourceUrl,
                    "eligibility_rules_json": product_item.eligibilityRules,
                    "target_segments_json": product_item.targetSegment,
                    "currencies_json": product_item.currency,
                    "active": product_item.active,
                },
            )
        )
    for ownership_item in batch.ownerships:
        session.execute(
            pg_insert(CustomerProduct)
            .values(
                id=deterministic_uuid(
                    "customer-product", ownership_item.customerId, ownership_item.productId
                ),
                customer_id=deterministic_uuid("customer", ownership_item.customerId),
                product_id=deterministic_uuid("product", ownership_item.productId),
                status=ownership_item.status,
                opened_on=ownership_item.openedOn,
                utilization_ratio=ownership_item.utilizationRatio,
                created_by="banking-integration",
            )
            .on_conflict_do_update(
                index_elements=[CustomerProduct.id],
                set_={
                    "status": ownership_item.status,
                    "utilization_ratio": ownership_item.utilizationRatio,
                },
            )
        )
    record = ProductImportReceipt(
        id=deterministic_uuid("import", "PRODUCTS", idempotency_key),
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        row_count=len(batch.products) + len(batch.ownerships),
        status="COMPLETED",
        correlation_id=correlation_id(request),
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    return {
        "jobId": str(record.id),
        "status": "COMPLETED",
        "imported": record.row_count,
    }


__all__ = ["app", "serialize"]
