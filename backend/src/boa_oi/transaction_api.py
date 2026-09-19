from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.ingestion import (
    SUPPORTED_CONTRACT_VERSION,
    canonical_model_hash,
    canonical_row_hash,
    claim_import_batch,
    import_batch_payload,
)
from boa_oi.models.entities import (
    ImportBatch,
    ImportRejectedRecord,
    Transaction,
    TransactionCategory,
    TransactionImportReceipt,
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
    "transaction-service",
    "Normalized transaction search and idempotent banking imports.",
)
PREFIX = "/internal/v1"


class StrictImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TransactionIn(StrictImportModel):
    transactionId: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    customerId: str = Field(min_length=1, max_length=40)
    accountId: str = Field(min_length=1, max_length=80)
    bookingDate: datetime
    valueDate: date
    type: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z][A-Z0-9_]*$")
    direction: Literal["CREDIT", "DEBIT"]
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="MAD", pattern=r"^[A-Z]{3}$")
    category: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    international: bool = False
    countryCode: str = Field(default="MA", pattern=r"^[A-Z]{2}$")
    status: str = Field(default="BOOKED", pattern=r"^[A-Z][A-Z0-9_]*$")
    sourceSystem: str = Field(
        default="BANKING_ADAPTER", min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$"
    )

    @field_validator("bookingDate")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bookingDate must include a timezone")
        return value


class TransactionBatch(StrictImportModel):
    contractVersion: str = Field(default=SUPPORTED_CONTRACT_VERSION, pattern=r"^\d+\.\d+$")
    sourceSystem: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    externalBatchId: str = Field(min_length=1, max_length=100)
    sourceWatermark: str | None = Field(default=None, max_length=120)
    producedAt: datetime | None = None
    expectedRowCount: int | None = Field(default=None, ge=0)
    transactions: list[TransactionIn] = Field(max_length=25_000)

    @field_validator("producedAt")
    @classmethod
    def produced_at_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("producedAt must include a timezone")
        return value

    @model_validator(mode="after")
    def supported_version(self) -> TransactionBatch:
        if self.contractVersion != SUPPORTED_CONTRACT_VERSION:
            raise ValueError(f"Only contractVersion {SUPPORTED_CONTRACT_VERSION} is supported")
        return self


class TransactionCategoryIn(StrictImportModel):
    categoryCode: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    version: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=120)
    active: bool = True
    provenance: Literal["SYNTHETIC_POC", "BOA_APPROVED", "EXTERNAL_CONTRACT"]
    reason: str = Field(min_length=10, max_length=500)


def serialize(tx: Transaction) -> dict[str, Any]:
    return {
        "transactionId": tx.transaction_ref,
        "customerId": str(tx.customer_id),
        "accountId": str(tx.account_id),
        "bookingDate": tx.booked_at.isoformat(),
        "valueDate": tx.value_date.isoformat(),
        "type": tx.transaction_type,
        "direction": tx.direction,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "category": tx.category,
        "international": tx.is_international,
        "countryCode": tx.country_code,
        "sourceSystem": tx.source_system,
        "externalReference": tx.transaction_ref,
        "categoryVersion": tx.category_version,
        "importBatchId": str(tx.import_batch_id) if tx.import_batch_id else None,
        "sourceRecordHash": tx.source_record_hash,
    }


def query_transactions(
    request: Request,
    session: Session,
    *,
    forced_customer: str | None = None,
    forced_account: str | None = None,
    page_size: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    reject_unknown_filters(
        request,
        {
            "pageSize",
            "cursor",
            "customerId",
            "accountId",
            "fromDate",
            "toDate",
            "type",
            "direction",
            "currency",
            "category",
            "international",
            "minAmount",
            "maxAmount",
            "sort",
        },
    )
    params = request.query_params
    offset = decode_cursor(cursor)
    stmt = select(Transaction)
    customer_id = forced_customer or params.get("customerId")
    account_id = forced_account or params.get("accountId")
    if customer_id:
        stmt = stmt.where(Transaction.customer_id == deterministic_uuid("customer", customer_id))
    if account_id:
        stmt = stmt.where(Transaction.account_id == deterministic_uuid("account", account_id))
    try:
        from_date = date.fromisoformat(params["fromDate"]) if params.get("fromDate") else None
        to_date = date.fromisoformat(params["toDate"]) if params.get("toDate") else None
        min_amount = Decimal(params["minAmount"]) if params.get("minAmount") else None
        max_amount = Decimal(params["maxAmount"]) if params.get("maxAmount") else None
    except (ValueError, ArithmeticError) as exc:
        raise Problem(422, "VALIDATION_ERROR", "Invalid transaction filter value.") from exc
    if from_date and to_date and to_date < from_date:
        raise Problem(422, "VALIDATION_ERROR", "toDate must be on or after fromDate.")
    if min_amount is not None and max_amount is not None and max_amount < min_amount:
        raise Problem(422, "VALIDATION_ERROR", "maxAmount must be greater than minAmount.")
    if from_date:
        stmt = stmt.where(Transaction.value_date >= from_date)
    if to_date:
        stmt = stmt.where(Transaction.value_date <= to_date)
    if params.get("type"):
        stmt = stmt.where(Transaction.transaction_type == params["type"])
    if params.get("direction"):
        stmt = stmt.where(Transaction.direction == params["direction"])
    if params.get("currency"):
        stmt = stmt.where(Transaction.currency == params["currency"])
    if params.get("category"):
        stmt = stmt.where(Transaction.category == params["category"])
    if params.get("international") is not None:
        international_value = params["international"].lower()
        if international_value not in {"true", "false"}:
            raise Problem(422, "VALIDATION_ERROR", "international must be true or false.")
        stmt = stmt.where(Transaction.is_international == (international_value == "true"))
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)
    sort = params.get("sort", "-valueDate")
    column = {
        "valueDate": Transaction.value_date,
        "amount": Transaction.amount,
        "bookingDate": Transaction.booked_at,
    }.get(sort.lstrip("-"))
    if column is None:
        raise Problem(400, "VALIDATION_ERROR", "Unsupported transaction sort field.")
    rows = list(
        session.scalars(
            stmt.order_by(column.desc() if sort.startswith("-") else column.asc(), Transaction.id)
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
    f"{PREFIX}/transactions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def list_transactions(
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return query_transactions(request, session, page_size=page_size, cursor=cursor)


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/transactions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def customer_transactions(
    customer_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return query_transactions(
        request,
        session,
        forced_customer=customer_id,
        page_size=page_size,
        cursor=cursor,
    )


@app.get(
    f"{PREFIX}/accounts/{{account_id}}/transactions",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def account_transactions(
    account_id: str,
    request: Request,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=1000)] = 25,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return query_transactions(
        request, session, forced_account=account_id, page_size=page_size, cursor=cursor
    )


ACTIVITY_GRANULARITIES = {"DAY": "day", "WEEK": "week", "MONTH": "month"}


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/activity",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def customer_activity(
    customer_id: str,
    request: Request,
    granularity: Annotated[str, Query(pattern="^(DAY|WEEK|MONTH)$")] = "MONTH",
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Série temporelle agrégée des mouvements d'une PME (aucune donnée synthétisée côté API :
    chaque point est une somme SQL sur les transactions importées)."""
    reject_unknown_filters(request, {"granularity", "fromDate", "toDate"})
    if from_date and to_date and to_date < from_date:
        raise Problem(422, "VALIDATION_ERROR", "toDate must be after fromDate.")
    bucket = func.date_trunc(ACTIVITY_GRANULARITIES[granularity], Transaction.value_date).label(
        "bucket"
    )
    credit = Transaction.direction == "CREDIT"
    debit = Transaction.direction == "DEBIT"
    stmt = (
        select(
            bucket,
            func.coalesce(func.sum(case((credit, Transaction.amount), else_=0)), 0).label("inflow"),
            func.coalesce(func.sum(case((debit, Transaction.amount), else_=0)), 0).label("outflow"),
            func.count(Transaction.id).label("transaction_count"),
            func.coalesce(
                func.sum(
                    case((Transaction.category == "SUPPLIER_PAYMENT", Transaction.amount), else_=0)
                ),
                0,
            ).label("supplier"),
            func.coalesce(
                func.sum(
                    case((Transaction.is_international.is_(True), Transaction.amount), else_=0)
                ),
                0,
            ).label("international"),
            func.sum(case((Transaction.is_international.is_(True), 1), else_=0)).label(
                "international_count"
            ),
        )
        .where(Transaction.customer_id == deterministic_uuid("customer", customer_id))
        .group_by(bucket)
        .order_by(bucket)
    )
    if from_date:
        stmt = stmt.where(Transaction.value_date >= from_date)
    if to_date:
        stmt = stmt.where(Transaction.value_date <= to_date)
    rows = session.execute(stmt).all()
    points = [
        {
            "period": row.bucket.date().isoformat()
            if hasattr(row.bucket, "date")
            else str(row.bucket),
            "inflow": float(row.inflow),
            "outflow": float(row.outflow),
            "net": float(row.inflow) - float(row.outflow),
            "transactionCount": int(row.transaction_count),
            "supplierPayments": float(row.supplier),
            "internationalAmount": float(row.international),
            "internationalCount": int(row.international_count or 0),
        }
        for row in rows
    ]
    return {
        "customerId": customer_id,
        "granularity": granularity,
        "currency": "MAD",
        "fromDate": from_date.isoformat()
        if from_date
        else (points[0]["period"] if points else None),
        "toDate": to_date.isoformat() if to_date else (points[-1]["period"] if points else None),
        "points": points,
        "source": "transaction-service aggregate (SQL)",
        "correlationId": correlation_id(request),
    }


@app.get(
    f"{PREFIX}/transactions/{{transaction_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Transactions"],
)
def get_transaction(
    transaction_id: str,
    source_system: Annotated[str | None, Query(alias="sourceSystem")] = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(Transaction).where(Transaction.transaction_ref == transaction_id)
    if source_system:
        stmt = stmt.where(Transaction.source_system == source_system)
    rows = list(session.scalars(stmt.order_by(Transaction.source_system).limit(2)))
    if not rows:
        raise not_found("Transaction")
    if len(rows) > 1:
        raise Problem(
            409,
            "AMBIGUOUS_TRANSACTION_REFERENCE",
            "sourceSystem is required because the reference exists in multiple sources.",
        )
    return serialize(rows[0])


def category_payload(row: TransactionCategory) -> dict[str, Any]:
    return {
        "categoryCode": row.category_code,
        "version": row.version,
        "label": row.label,
        "active": row.active,
        "provenance": row.provenance,
        "checksum": row.checksum,
        "reason": row.reason,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "createdBy": row.created_by,
    }


@app.get(
    f"{PREFIX}/transaction-categories",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def list_transaction_categories(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(TransactionCategory).order_by(
                TransactionCategory.category_code, TransactionCategory.version.desc()
            )
        )
    )
    return {"data": [category_payload(row) for row in rows]}


@app.post(
    f"{PREFIX}/transaction-categories",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def create_transaction_category(
    payload: TransactionCategoryIn,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    existing = session.scalar(
        select(TransactionCategory).where(
            TransactionCategory.category_code == payload.categoryCode,
            TransactionCategory.version == payload.version,
        )
    )
    if existing is not None:
        raise Problem(409, "CATEGORY_VERSION_EXISTS", "This category version already exists.")
    if payload.active:
        session.execute(
            update(TransactionCategory)
            .where(TransactionCategory.category_code == payload.categoryCode)
            .values(active=False)
        )
    checksum = canonical_row_hash(payload.model_dump(mode="json"))
    row = TransactionCategory(
        id=deterministic_uuid("transaction-category", payload.categoryCode, payload.version),
        category_code=payload.categoryCode,
        version=payload.version,
        label=payload.label,
        active=payload.active,
        provenance=payload.provenance,
        checksum=checksum,
        reason=payload.reason,
        created_by=principal.username,
    )
    session.add(row)
    session.flush()
    return category_payload(row)


def active_category_versions(session: Session) -> dict[str, str]:
    return {
        str(code): str(version)
        for code, version in session.execute(
            select(TransactionCategory.category_code, TransactionCategory.version).where(
                TransactionCategory.active.is_(True)
            )
        ).all()
    }


def rejection_payload(row: ImportRejectedRecord) -> dict[str, Any]:
    return {
        "rejectionId": str(row.id),
        "rowNumber": row.row_number,
        "sourceRecordRef": row.source_record_ref,
        "rowHash": row.row_hash,
        "reasonCode": row.reason_code,
        "field": row.field_name,
        "safeDetails": row.safe_details_json,
        "status": row.status,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


@app.get(
    f"{PREFIX}/imports/transactions/{{job_id}}",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def get_transaction_import(job_id: UUID, session: Session = Depends(get_session)) -> dict[str, Any]:
    record = session.get(ImportBatch, job_id)
    if record is None or record.source_system == "ANALYTICS_PIPELINE":
        raise not_found("Import batch")
    return import_batch_payload(record)


@app.get(
    f"{PREFIX}/imports/transactions/{{job_id}}/rejections",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def get_transaction_import_rejections(
    job_id: UUID, session: Session = Depends(get_session)
) -> dict[str, Any]:
    record = session.get(ImportBatch, job_id)
    if record is None:
        raise not_found("Import batch")
    rows = list(
        session.scalars(
            select(ImportRejectedRecord)
            .where(
                ImportRejectedRecord.batch_id == job_id,
                ImportRejectedRecord.domain == "TRANSACTION",
            )
            .order_by(ImportRejectedRecord.row_number)
        )
    )
    return {"jobId": str(job_id), "data": [rejection_payload(row) for row in rows]}


@app.post(
    f"{PREFIX}/imports/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Imports"],
)
def import_transactions(
    batch: TransactionBatch,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    body_hash = canonical_model_hash(batch)
    existing = session.scalar(
        select(TransactionImportReceipt).where(
            TransactionImportReceipt.idempotency_key == idempotency_key
        )
    )
    if existing:
        if existing.request_hash != body_hash:
            raise Problem(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was reused with different content.",
            )
        existing_manifest = session.scalar(
            select(ImportBatch).where(
                ImportBatch.source_system == batch.sourceSystem,
                ImportBatch.batch_ref == batch.externalBatchId,
            )
        )
        if existing_manifest is None:
            raise Problem(
                409,
                "IMPORT_MANIFEST_MISSING",
                "The legacy receipt exists without a governed import manifest.",
            )
        response = import_batch_payload(existing_manifest)
        response["imported"] = existing.row_count
        return response
    corr = correlation_id(request)
    manifest, replay = claim_import_batch(
        session,
        source_system=batch.sourceSystem,
        external_batch_id=batch.externalBatchId,
        contract_version=batch.contractVersion,
        payload_hash=body_hash,
        correlation_id=corr,
        expected_row_count=batch.expectedRowCount,
        received_row_count=len(batch.transactions),
        source_watermark=batch.sourceWatermark,
        produced_at=batch.producedAt,
    )
    if replay:
        response = import_batch_payload(manifest)
        response["imported"] = manifest.accepted_count
        return response

    manifest.status = "VALIDATING"
    category_versions = active_category_versions(session)
    seen: dict[tuple[str, str], str] = {}
    valid_values: list[dict[str, Any]] = []
    quarantines: list[ImportRejectedRecord] = []
    duplicate_count = 0
    for row_number, item in enumerate(batch.transactions, start=1):
        raw = item.model_dump(mode="json")
        row_hash = canonical_row_hash(raw)
        source_key = (item.sourceSystem, item.transactionId)
        if source_key in seen:
            if seen[source_key] == row_hash:
                duplicate_count += 1
                continue
            reason_code = "DUPLICATE_SOURCE_RECORD_CONFLICT"
            field_name = "transactionId"
        elif item.category not in category_versions:
            reason_code = "UNKNOWN_OR_INACTIVE_CATEGORY"
            field_name = "category"
        else:
            seen[source_key] = row_hash
            valid_values.append(
                {
                    "id": deterministic_uuid("transaction", item.sourceSystem, item.transactionId),
                    "transaction_ref": item.transactionId,
                    "customer_id": deterministic_uuid("customer", item.customerId),
                    "account_id": deterministic_uuid("account", item.accountId),
                    "booked_at": item.bookingDate,
                    "value_date": item.valueDate,
                    "direction": item.direction,
                    "amount": item.amount,
                    "currency": item.currency,
                    "transaction_type": item.type,
                    "category": item.category,
                    "category_version": category_versions[item.category],
                    "is_international": item.international,
                    "country_code": item.countryCode,
                    "status": item.status,
                    "source_system": item.sourceSystem,
                    "import_batch_id": manifest.id,
                    "source_record_hash": row_hash,
                    "created_by": "governed-ingestion",
                }
            )
            continue
        quarantines.append(
            ImportRejectedRecord(
                id=deterministic_uuid("import-rejection", manifest.id, row_number),
                batch_id=manifest.id,
                domain="TRANSACTION",
                row_number=row_number,
                source_record_ref=item.transactionId,
                row_hash=row_hash,
                reason_code=reason_code,
                field_name=field_name,
                safe_details_json={
                    "sourceSystem": item.sourceSystem,
                    "category": item.category,
                },
                status="QUARANTINED",
                correlation_id=corr,
            )
        )

    manifest.status = "APPLYING"
    inserted: set[tuple[str, str]] = set()
    chunk = 5_000
    for index in range(0, len(valid_values), chunk):
        result = session.execute(
            pg_insert(Transaction)
            .values(valid_values[index : index + chunk])
            .on_conflict_do_nothing(
                index_elements=[Transaction.source_system, Transaction.transaction_ref]
            )
            .returning(Transaction.source_system, Transaction.transaction_ref)
        )
        inserted.update((str(row[0]), str(row[1])) for row in result.all())
    duplicate_count += len(valid_values) - len(inserted)
    session.add_all(quarantines)

    received = len(batch.transactions)
    expected_matches = batch.expectedRowCount is None or batch.expectedRowCount == received
    manifest.accepted_count = len(inserted)
    manifest.duplicate_count = duplicate_count
    manifest.rejected_count = 0
    manifest.quarantined_count = len(quarantines)
    manifest.row_count = received
    manifest.received_row_count = received
    manifest.quality_status = "PASS" if not quarantines and expected_matches else "WARNING"
    manifest.status = "COMPLETED" if not quarantines else "QUARANTINED"
    manifest.completed_at = datetime.now(timezone.utc)
    freshness = (manifest.quality_json or {}).get("freshness", {})
    manifest.quality_json = {
        "contractVersion": batch.contractVersion,
        "completeness": {
            "expected": batch.expectedRowCount,
            "received": received,
            "status": (
                "UNKNOWN"
                if batch.expectedRowCount is None
                else ("PASS" if expected_matches else "FAIL")
            ),
        },
        "freshness": freshness,
        "categories": {
            "catalogued": len(category_versions),
            "unknownOrInactive": len(quarantines),
        },
        "dataKind": "SOURCE_PROVIDED_OR_SYNTHETIC_POC",
        "productionClaim": False,
    }
    record = TransactionImportReceipt(
        id=deterministic_uuid("import", "TRANSACTIONS", idempotency_key),
        idempotency_key=idempotency_key,
        request_hash=body_hash,
        row_count=len(inserted),
        status=manifest.status,
        correlation_id=corr,
        created_at=datetime.now(timezone.utc),
    )
    session.add(record)
    response = import_batch_payload(manifest)
    response["imported"] = len(inserted)
    return response


__all__ = ["app", "serialize"]
