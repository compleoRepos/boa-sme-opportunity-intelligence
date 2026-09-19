from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from boa_oi.http_clients import HttpBankingAdapter, service_request
from boa_oi.ingestion import (
    SUPPORTED_CONTRACT_VERSION,
    canonical_model_hash,
    claim_import_batch,
    import_batch_payload,
)
from boa_oi.models.entities import ImportBatch
from boa_oi.platform import (
    ADMIN_ROLES,
    Problem,
    correlation_id,
    create_service_app,
    get_session,
    require_roles,
)

app = create_service_app(
    "banking-integration-service",
    "HTTP anti-corruption layer between banking adapters and domain services.",
)
PREFIX = "/internal/v1"


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contractVersion: str = Field(default=SUPPORTED_CONTRACT_VERSION, pattern=r"^\d+\.\d+$")
    fromDate: date
    toDate: date
    customerCount: int = Field(default=8, ge=1, le=500)
    customerIds: list[str] | None = None
    source: str = "ALL"
    sourceWatermark: str | None = Field(default=None, max_length=120)
    producedAt: datetime | None = None

    @field_validator("producedAt")
    @classmethod
    def produced_at_timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("producedAt must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> ImportRequest:
        if self.contractVersion != SUPPORTED_CONTRACT_VERSION:
            raise ValueError(f"Only contractVersion {SUPPORTED_CONTRACT_VERSION} is supported")
        if self.toDate < self.fromDate:
            raise ValueError("toDate must be on or after fromDate")
        return self


def service_url(name: str) -> str:
    value = os.getenv(f"{name.upper()}_SERVICE_URL")
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{name.upper()}_SERVICE_URL is not configured.",
        )
    return value.rstrip("/")


def validate_downstream_import_response(response: Any, service: str) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise Problem(
            502,
            "DOWNSTREAM_IMPORT_INCOMPLETE",
            f"{service} returned an invalid import response.",
        )
    job_id = response.get("jobId")
    imported = response.get("imported")
    if (
        response.get("status") != "COMPLETED"
        or not isinstance(job_id, str)
        or not job_id
        or isinstance(imported, bool)
        or not isinstance(imported, int)
        or imported < 0
    ):
        raise Problem(
            502,
            "DOWNSTREAM_IMPORT_INCOMPLETE",
            f"{service} did not confirm a complete governed import.",
        )
    if service == "transaction":
        counts = response.get("counts")
        if not isinstance(counts, dict) or counts.get("accepted") != imported:
            raise Problem(
                502,
                "DOWNSTREAM_IMPORT_INCOMPLETE",
                "transaction returned inconsistent governed import counters.",
            )
    return response


@app.post(
    f"{PREFIX}/imports/all",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def import_all(
    payload: ImportRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    corr = correlation_id(request)
    body_hash = canonical_model_hash(payload)
    record, replay = claim_import_batch(
        session,
        source_system="BANKING_HTTP",
        external_batch_id=idempotency_key,
        contract_version=payload.contractVersion,
        payload_hash=body_hash,
        correlation_id=corr,
        expected_row_count=None,
        received_row_count=0,
        source_watermark=payload.sourceWatermark,
        produced_at=payload.producedAt,
    )
    if replay:
        response = import_batch_payload(record)
        response["imported"] = record.accepted_count
        return response
    record.status = "VALIDATING"
    session.commit()

    adapter = HttpBankingAdapter()
    responses: list[dict[str, Any]] = []
    try:
        customers = await adapter.fetch_customers(payload.customerCount, corr)
        accounts = await adapter.fetch_accounts(payload.customerCount, corr)
        balances = await adapter.fetch_balances(payload.customerCount, corr)
        transactions = await adapter.fetch_transactions(
            payload.fromDate, payload.toDate, payload.customerCount, corr
        )
        products = await adapter.fetch_products(payload.customerCount, corr)
        row_count = (
            len(customers)
            + len(accounts)
            + len(balances)
            + len(transactions)
            + len(products["ownerships"])
        )
        record = session.get(ImportBatch, record.id) or record
        record.row_count = row_count
        record.received_row_count = row_count
        record.status = "APPLYING"
        record.quality_status = "UNKNOWN"
        record.quality_json = {
            "qualityEvidence": "PARTIAL_UNTIL_ALL_DOMAIN_SERVICES_ARE_GOVERNED",
            "dataKind": "SOURCE_PROVIDED_OR_SYNTHETIC_POC",
            "productionClaim": False,
        }
        session.commit()

        batch_id = f"banking-{idempotency_key}"
        responses.append(
            validate_downstream_import_response(
                await service_request(
                    "POST",
                    f"{service_url('customer')}/internal/v1/imports/customers",
                    correlation_id=corr,
                    idempotency_key=f"{idempotency_key}-customers",
                    json={
                        "sourceSystem": "BANKING_HTTP",
                        "externalBatchId": batch_id,
                        "customers": customers,
                    },
                    timeout=30,
                ),
                "customer",
            )
        )
        responses.append(
            validate_downstream_import_response(
                await service_request(
                    "POST",
                    f"{service_url('account')}/internal/v1/imports/accounts",
                    correlation_id=corr,
                    idempotency_key=f"{idempotency_key}-accounts",
                    json={
                        "externalBatchId": batch_id,
                        "accounts": accounts,
                        "balances": balances,
                    },
                    timeout=90,
                ),
                "account",
            )
        )
        responses.append(
            validate_downstream_import_response(
                await service_request(
                    "POST",
                    f"{service_url('transaction')}/internal/v1/imports/transactions",
                    correlation_id=corr,
                    idempotency_key=f"{idempotency_key}-transactions",
                    json={
                        "contractVersion": payload.contractVersion,
                        "sourceSystem": "BANKING_HTTP",
                        "externalBatchId": batch_id,
                        "sourceWatermark": payload.sourceWatermark,
                        "producedAt": (
                            payload.producedAt.isoformat() if payload.producedAt else None
                        ),
                        "expectedRowCount": len(transactions),
                        "transactions": transactions,
                    },
                    timeout=120,
                ),
                "transaction",
            )
        )
        responses.append(
            validate_downstream_import_response(
                await service_request(
                    "POST",
                    f"{service_url('product')}/internal/v1/imports/products",
                    correlation_id=corr,
                    idempotency_key=f"{idempotency_key}-products",
                    json={"externalBatchId": batch_id, **products},
                    timeout=30,
                ),
                "product",
            )
        )
    except Exception:
        failed_record = session.get(ImportBatch, record.id) or record
        failed_record.status = "PARTIAL" if responses else "RETRYABLE_FAILED"
        failed_record.quality_status = "FAIL"
        failed_record.completed_at = datetime.now(timezone.utc)
        failed_record.quality_json = {
            **(failed_record.quality_json or {}),
            "completedServices": len(responses),
            "failure": "DOWNSTREAM_IMPORT_FAILED",
            "reconciliationRequired": bool(responses),
        }
        session.commit()
        raise

    completed_record = session.get(ImportBatch, record.id) or record
    imported = sum(
        int(response.get("imported", 0)) for response in responses if isinstance(response, dict)
    )
    completed_record.accepted_count = imported
    completed_record.status = "COMPLETED"
    completed_record.quality_status = "WARNING"
    completed_record.completed_at = datetime.now(timezone.utc)
    completed_record.quality_json = {
        **(completed_record.quality_json or {}),
        "completedServices": len(responses),
        "serviceCount": 4,
        "qualityEvidence": "TRANSACTION_GOVERNED_OTHER_DOMAINS_LEGACY",
    }
    response = import_batch_payload(completed_record)
    response["imported"] = imported
    response["services"] = responses
    return response


@app.post(
    f"{PREFIX}/imports/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def import_transactions(
    payload: ImportRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> dict[str, Any]:
    corr = correlation_id(request)
    rows = await HttpBankingAdapter().fetch_transactions(
        payload.fromDate, payload.toDate, payload.customerCount, corr
    )
    return await service_request(
        "POST",
        f"{service_url('transaction')}/internal/v1/imports/transactions",
        correlation_id=corr,
        idempotency_key=idempotency_key,
        json={
            "contractVersion": payload.contractVersion,
            "sourceSystem": "BANKING_HTTP",
            "externalBatchId": idempotency_key,
            "sourceWatermark": payload.sourceWatermark,
            "producedAt": payload.producedAt.isoformat() if payload.producedAt else None,
            "expectedRowCount": len(rows),
            "transactions": rows,
        },
        timeout=120,
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/external-profile",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def external_profile(customer_id: str, request: Request) -> dict[str, Any]:
    adapter = HttpBankingAdapter()
    return await service_request(
        "GET",
        f"{adapter.base_url}/mock/v1/customers/{customer_id}/external-profile",
        correlation_id=correlation_id(request),
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/international-flows",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def external_flows(customer_id: str, request: Request) -> list[dict[str, Any]]:
    adapter = HttpBankingAdapter()
    return await service_request(
        "GET",
        f"{adapter.base_url}/mock/v1/customers/{customer_id}/international-flows",
        correlation_id=correlation_id(request),
    )


@app.get(
    f"{PREFIX}/customers/{{customer_id}}/trade-finance-ownership",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Banking Integration"],
)
async def trade_ownership(customer_id: str, request: Request) -> dict[str, Any]:
    adapter = HttpBankingAdapter()
    return await service_request(
        "GET",
        f"{adapter.base_url}/mock/v1/customers/{customer_id}/trade-finance-ownership",
        correlation_id=correlation_id(request),
    )


__all__ = ["app"]
