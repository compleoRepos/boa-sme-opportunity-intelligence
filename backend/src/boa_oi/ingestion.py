from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from boa_oi.models.entities import ImportBatch
from boa_oi.platform import Problem
from boa_oi.technical.ids import deterministic_uuid

SUPPORTED_CONTRACT_VERSION = "1.0"
TERMINAL_BATCH_STATUSES = {"COMPLETED", "QUARANTINED", "REJECTED"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_model_hash(model: BaseModel) -> str:
    return hashlib.sha256(canonical_json(model.model_dump(mode="json")).encode()).hexdigest()


def canonical_row_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def measured_freshness(
    produced_at: datetime | None, received_at: datetime
) -> tuple[int | None, str, dict[str, Any]]:
    if produced_at is None:
        return (
            None,
            "UNKNOWN",
            {
                "assessment": "UNKNOWN",
                "reason": "SOURCE_TIMESTAMP_NOT_PROVIDED",
            },
        )
    lag_seconds = max(0, int((received_at - produced_at).total_seconds()))
    return (
        lag_seconds,
        "UNKNOWN",
        {
            "assessment": "MEASURED_WITHOUT_THRESHOLD",
            "lagSeconds": lag_seconds,
            "threshold": None,
            "disclaimer": "HYPOTHÈSE À VALIDER AVEC BOA",
        },
    )


def claim_import_batch(
    session: Session,
    *,
    source_system: str,
    external_batch_id: str,
    contract_version: str,
    payload_hash: str,
    correlation_id: str,
    expected_row_count: int | None,
    received_row_count: int,
    source_watermark: str | None,
    produced_at: datetime | None,
) -> tuple[ImportBatch, bool]:
    if contract_version != SUPPORTED_CONTRACT_VERSION:
        raise Problem(
            422,
            "UNSUPPORTED_CONTRACT_VERSION",
            f"Only contractVersion {SUPPORTED_CONTRACT_VERSION} is supported.",
        )
    now = datetime.now(timezone.utc)
    batch_id = deterministic_uuid("governed-import-batch", source_system, external_batch_id)
    lag_seconds, freshness_status, freshness_json = measured_freshness(produced_at, now)
    statement = (
        pg_insert(ImportBatch)
        .values(
            id=batch_id,
            source_system=source_system,
            batch_ref=external_batch_id,
            external_batch_id=external_batch_id,
            contract_version=contract_version,
            started_at=now,
            completed_at=None,
            input_hash=payload_hash,
            row_count=received_row_count,
            received_at=now,
            expected_row_count=expected_row_count,
            received_row_count=received_row_count,
            accepted_count=0,
            duplicate_count=0,
            rejected_count=0,
            quarantined_count=0,
            quality_status="UNKNOWN",
            freshness_status=freshness_status,
            freshness_lag_seconds=lag_seconds,
            source_watermark=source_watermark,
            produced_at=produced_at,
            quality_json={"freshness": freshness_json},
            status="RECEIVED",
            correlation_id=correlation_id,
        )
        .on_conflict_do_nothing(index_elements=[ImportBatch.source_system, ImportBatch.batch_ref])
        .returning(ImportBatch.id)
    )
    inserted_id = session.scalar(statement)
    record = session.scalar(
        select(ImportBatch).where(
            ImportBatch.source_system == source_system,
            ImportBatch.batch_ref == external_batch_id,
        )
    )
    if record is None:
        raise Problem(500, "IMPORT_CLAIM_FAILED", "The import batch could not be claimed.")
    if record.input_hash != payload_hash:
        raise Problem(
            409,
            "IDEMPOTENCY_KEY_REUSED",
            "The source batch was reused with different content.",
        )
    is_replay = inserted_id is None
    if is_replay and record.status not in TERMINAL_BATCH_STATUSES:
        raise Problem(
            409,
            "IMPORT_ALREADY_IN_PROGRESS",
            "The source batch is already being processed.",
        )
    return record, is_replay


def import_batch_payload(record: ImportBatch) -> dict[str, Any]:
    return {
        "jobId": str(record.id),
        "contractVersion": record.contract_version,
        "sourceSystem": record.source_system,
        "externalBatchId": record.external_batch_id or record.batch_ref,
        "status": record.status,
        "counts": {
            "expected": record.expected_row_count,
            "received": record.received_row_count,
            "accepted": record.accepted_count,
            "duplicate": record.duplicate_count,
            "rejected": record.rejected_count,
            "quarantined": record.quarantined_count,
        },
        "quality": {
            "status": record.quality_status,
            "details": record.quality_json,
        },
        "freshness": {
            "status": record.freshness_status,
            "lagSeconds": record.freshness_lag_seconds,
            "sourceWatermark": record.source_watermark,
            "producedAt": record.produced_at.isoformat() if record.produced_at else None,
            "receivedAt": record.received_at.isoformat() if record.received_at else None,
            "threshold": None,
        },
        "correlationId": record.correlation_id,
    }


__all__ = [
    "SUPPORTED_CONTRACT_VERSION",
    "canonical_model_hash",
    "canonical_row_hash",
    "claim_import_batch",
    "import_batch_payload",
    "measured_freshness",
]
