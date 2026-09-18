from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.models.entities import CustomerProduct, Product, ProductImportReceipt
from boa_oi.platform import (
    ADMIN_ROLES,
    READ_ROLES,
    Problem,
    correlation_id,
    create_service_app,
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


class ProductIn(BaseModel):
    productId: str
    name: str
    category: str
    eligibilityRules: dict[str, Any] = Field(default_factory=dict)
    targetSegment: list[str] = Field(default_factory=lambda: ["SMALL", "MEDIUM"])
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


def serialize(product: Product) -> dict[str, Any]:
    return {
        "productId": product.product_code,
        "name": product.name,
        "category": product.category,
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
    if active is not None:
        stmt = stmt.where(Product.active == active)
    if request.query_params.get("q"):
        stmt = stmt.where(Product.name.ilike(f"%{request.query_params['q']}%"))
    column = {
        "name": Product.name,
        "category": Product.category,
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
        total_count=session.scalar(select(func.count()).select_from(Product)),
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
def customer_products(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 100,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
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
def product_gaps(customer_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
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
