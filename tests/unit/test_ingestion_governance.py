from __future__ import annotations

from datetime import datetime, timezone

import pytest
from boa_oi.banking_integration_api import validate_downstream_import_response
from boa_oi.ingestion import canonical_model_hash, measured_freshness
from boa_oi.platform import Problem
from boa_oi.transaction_api import TransactionBatch
from pydantic import ValidationError


def valid_payload() -> dict:
    return {
        "contractVersion": "1.0",
        "sourceSystem": "BANKING_HTTP",
        "externalBatchId": "batch-001",
        "sourceWatermark": "wm-001",
        "producedAt": "2026-09-19T10:00:00+00:00",
        "expectedRowCount": 1,
        "transactions": [
            {
                "transactionId": "TX-001",
                "customerId": "SME-00001",
                "accountId": "ACC-00001",
                "bookingDate": "2026-09-19T10:00:00+00:00",
                "valueDate": "2026-09-19",
                "type": "PAYMENT",
                "direction": "DEBIT",
                "amount": "100.25",
                "currency": "MAD",
                "category": "SUPPLIER_PAYMENT",
                "international": False,
                "countryCode": "MA",
                "status": "BOOKED",
                "sourceSystem": "MOCK_PAYMENTS",
            }
        ],
    }


def test_transaction_contract_is_strict_versioned_and_timezone_aware() -> None:
    payload = valid_payload()
    batch = TransactionBatch.model_validate(payload)
    assert batch.contractVersion == "1.0"
    assert batch.transactions[0].bookingDate.tzinfo is not None

    with pytest.raises(ValidationError):
        TransactionBatch.model_validate({**payload, "unexpected": True})
    with pytest.raises(ValidationError):
        TransactionBatch.model_validate({**payload, "contractVersion": "2.0"})

    invalid_timezone = valid_payload()
    invalid_timezone["transactions"][0]["bookingDate"] = "2026-09-19T10:00:00"
    with pytest.raises(ValidationError):
        TransactionBatch.model_validate(invalid_timezone)


def test_canonical_hash_is_stable_for_equivalent_contracts() -> None:
    first = TransactionBatch.model_validate(valid_payload())
    reordered = dict(reversed(list(valid_payload().items())))
    second = TransactionBatch.model_validate(reordered)
    assert canonical_model_hash(first) == canonical_model_hash(second)


def test_freshness_without_source_timestamp_remains_unknown() -> None:
    lag, status, evidence = measured_freshness(None, datetime.now(timezone.utc))
    assert lag is None
    assert status == "UNKNOWN"
    assert evidence == {
        "assessment": "UNKNOWN",
        "reason": "SOURCE_TIMESTAMP_NOT_PROVIDED",
    }


def test_measured_freshness_has_no_invented_threshold() -> None:
    produced = datetime(2026, 9, 19, 10, tzinfo=timezone.utc)
    received = datetime(2026, 9, 19, 10, 5, tzinfo=timezone.utc)
    lag, status, evidence = measured_freshness(produced, received)
    assert lag == 300
    assert status == "UNKNOWN"
    assert evidence["assessment"] == "MEASURED_WITHOUT_THRESHOLD"
    assert evidence["threshold"] is None
    assert evidence["disclaimer"] == "HYPOTHÈSE À VALIDER AVEC BOA"


def test_downstream_import_requires_semantic_completion() -> None:
    completed = {"jobId": "job-1", "status": "COMPLETED", "imported": 2}
    assert validate_downstream_import_response(completed, "customer") == completed

    for invalid in (
        {"jobId": "job-1", "status": "PARTIAL", "imported": 2},
        {"status": "COMPLETED", "imported": 2},
        {"jobId": "job-1", "status": "COMPLETED"},
        ["not", "an", "object"],
    ):
        with pytest.raises(Problem) as raised:
            validate_downstream_import_response(invalid, "customer")
        assert raised.value.status_code == 502
        assert raised.value.code == "DOWNSTREAM_IMPORT_INCOMPLETE"


def test_transaction_downstream_counts_must_match_imported() -> None:
    completed = {
        "jobId": "job-transaction",
        "status": "COMPLETED",
        "imported": 1,
        "counts": {"accepted": 1, "duplicate": 0, "quarantined": 0},
    }
    assert validate_downstream_import_response(completed, "transaction") == completed

    inconsistent = {**completed, "counts": {"accepted": 0}}
    with pytest.raises(Problem) as raised:
        validate_downstream_import_response(inconsistent, "transaction")
    assert raised.value.code == "DOWNSTREAM_IMPORT_INCOMPLETE"
