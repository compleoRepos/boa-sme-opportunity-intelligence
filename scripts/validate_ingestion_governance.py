from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine, text


def principal_header() -> dict[str, str]:
    payload = {
        "subject": "ingestion-governance-test",
        "username": "ingestion-governance-test",
        "roles": ["ADMIN"],
        "relationshipManagerIds": [],
        "branchIds": [],
    }
    return {"X-Dev-Principal": json.dumps(payload, separators=(",", ":"))}


def transaction(
    transaction_id: str,
    *,
    category: str,
    source: str = "MOCK_PAYMENTS",
    amount: str = "100.25",
) -> dict[str, Any]:
    return {
        "transactionId": transaction_id,
        "customerId": "SME-GOV-001",
        "accountId": "ACC-GOV-001",
        "bookingDate": "2026-09-19T10:00:00+00:00",
        "valueDate": "2026-09-19",
        "type": "PAYMENT",
        "direction": "DEBIT",
        "amount": amount,
        "currency": "MAD",
        "category": category,
        "international": False,
        "countryCode": "MA",
        "status": "BOOKED",
        "sourceSystem": source,
    }


def batch(
    external_batch_id: str,
    rows: list[dict[str, Any]],
    *,
    source: str = "BANKING_HTTP",
) -> dict[str, Any]:
    return {
        "contractVersion": "1.0",
        "sourceSystem": source,
        "externalBatchId": external_batch_id,
        "sourceWatermark": "watermark-2026-09-19",
        "producedAt": "2026-09-19T10:05:00+00:00",
        "expectedRowCount": len(rows),
        "transactions": rows,
    }


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    expected: int,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.request(method, url, headers=headers, json=payload)
    if response.status_code != expected:
        raise AssertionError(
            f"{method} {url}: expected {expected}, got {response.status_code}: "
            f"{response.text[:500]}"
        )
    return response.json()


async def wait_ready(client: httpx.AsyncClient, base_url: str) -> None:
    deadline = asyncio.get_running_loop().time() + 60
    while asyncio.get_running_loop().time() < deadline:
        try:
            response = await client.get(f"{base_url}/ready")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("transaction service did not become ready")


async def run(output: Path) -> dict[str, Any]:
    base_url = os.getenv("INGESTION_TRANSACTION_URL", "http://ingestion-transaction:8080")
    database_url = os.environ["INGESTION_DATABASE_URL"]
    admin = principal_header()
    checks: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        await wait_ready(client, base_url)
        known = transaction("TX-GOV-001", category="SUPPLIER_PAYMENT")
        unknown = transaction("TX-GOV-002", category="UNMAPPED_SOURCE_CATEGORY")
        second_known = transaction("TX-GOV-003", category="CUSTOMER_RECEIPT")
        governed_batch = batch("batch-governed-001", [known, unknown, known, second_known])
        headers = {**admin, "Idempotency-Key": "idem-governed-001"}
        first = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/imports/transactions",
            expected=202,
            headers=headers,
            payload=governed_batch,
        )
        assert first["status"] == "QUARANTINED"
        assert first["counts"] == {
            "expected": 4,
            "received": 4,
            "accepted": 2,
            "duplicate": 1,
            "rejected": 0,
            "quarantined": 1,
        }
        assert first["quality"]["status"] == "WARNING"
        assert first["freshness"]["status"] == "UNKNOWN"
        assert first["freshness"]["threshold"] is None
        checks.append({"name": "partial-acceptance-and-quarantine", "status": "PASS"})

        status_payload = await request_json(
            client,
            "GET",
            f"{base_url}/internal/v1/imports/transactions/{first['jobId']}",
            expected=200,
            headers=admin,
        )
        assert status_payload["counts"] == first["counts"]
        rejection_payload = await request_json(
            client,
            "GET",
            f"{base_url}/internal/v1/imports/transactions/{first['jobId']}/rejections",
            expected=200,
            headers=admin,
        )
        assert len(rejection_payload["data"]) == 1
        rejection = rejection_payload["data"][0]
        assert rejection["reasonCode"] == "UNKNOWN_OR_INACTIVE_CATEGORY"
        assert set(rejection["safeDetails"]) == {"sourceSystem", "category"}
        checks.append({"name": "redacted-rejection-evidence", "status": "PASS"})

        replay = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/imports/transactions",
            expected=202,
            headers=headers,
            payload=governed_batch,
        )
        assert replay["jobId"] == first["jobId"]
        assert replay["counts"] == first["counts"]
        changed = json.loads(json.dumps(governed_batch))
        changed["transactions"][0]["amount"] = "999.00"
        conflict = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/imports/transactions",
            expected=409,
            headers=headers,
            payload=changed,
        )
        assert conflict["code"] == "IDEMPOTENCY_KEY_REUSED"
        checks.append({"name": "idempotent-replay-and-conflict", "status": "PASS"})

        strict = json.loads(json.dumps(governed_batch))
        strict["unexpected"] = True
        validation = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/imports/transactions",
            expected=422,
            headers={**admin, "Idempotency-Key": "idem-governed-strict"},
            payload=strict,
        )
        assert validation["code"] == "VALIDATION_ERROR"
        invalid_filter = await request_json(
            client,
            "GET",
            f"{base_url}/internal/v1/transactions?international=maybe",
            expected=422,
            headers=admin,
        )
        assert invalid_filter["code"] == "VALIDATION_ERROR"
        checks.append({"name": "strict-contract-and-filter-validation", "status": "PASS"})

        category = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/transaction-categories",
            expected=201,
            headers=admin,
            payload={
                "categoryCode": "TEST_POC_CATEGORY",
                "version": "poc-test-v1",
                "label": "Catégorie POC de validation",
                "active": True,
                "provenance": "SYNTHETIC_POC",
                "reason": "Validation technique locale sur données synthétiques uniquement.",
            },
        )
        assert category["provenance"] == "SYNTHETIC_POC"
        assert len(category["checksum"]) == 64
        category_rows = [transaction("TX-GOV-004", category="TEST_POC_CATEGORY")]
        category_import = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/imports/transactions",
            expected=202,
            headers={**admin, "Idempotency-Key": "idem-governed-category"},
            payload=batch("batch-governed-category", category_rows),
        )
        assert category_import["status"] == "COMPLETED"
        assert category_import["counts"]["accepted"] == 1
        checks.append({"name": "versioned-category-catalog", "status": "PASS"})

        other_source_rows = [
            transaction(
                "TX-GOV-001",
                category="SUPPLIER_PAYMENT",
                source="MOCK_SECONDARY",
            )
        ]
        other_source = await request_json(
            client,
            "POST",
            f"{base_url}/internal/v1/imports/transactions",
            expected=202,
            headers={**admin, "Idempotency-Key": "idem-governed-source"},
            payload=batch(
                "batch-governed-source",
                other_source_rows,
                source="BANKING_HTTP_SECONDARY",
            ),
        )
        assert other_source["counts"]["accepted"] == 1
        ambiguous = await request_json(
            client,
            "GET",
            f"{base_url}/internal/v1/transactions/TX-GOV-001",
            expected=409,
            headers=admin,
        )
        assert ambiguous["code"] == "AMBIGUOUS_TRANSACTION_REFERENCE"
        sourced = await request_json(
            client,
            "GET",
            f"{base_url}/internal/v1/transactions/TX-GOV-001?sourceSystem=MOCK_SECONDARY",
            expected=200,
            headers=admin,
        )
        assert sourced["sourceSystem"] == "MOCK_SECONDARY"
        checks.append({"name": "source-scoped-transaction-identity", "status": "PASS"})

        concurrent_payload = batch(
            "batch-governed-concurrent",
            [transaction("TX-GOV-005", category="OPERATING_EXPENSE")],
        )
        concurrent_headers = {**admin, "Idempotency-Key": "idem-governed-concurrent"}

        async def concurrent_call() -> httpx.Response:
            return await client.post(
                f"{base_url}/internal/v1/imports/transactions",
                headers=concurrent_headers,
                json=concurrent_payload,
            )

        concurrent_responses = await asyncio.gather(concurrent_call(), concurrent_call())
        assert [response.status_code for response in concurrent_responses] == [202, 202]
        concurrent_json = [response.json() for response in concurrent_responses]
        assert concurrent_json[0]["jobId"] == concurrent_json[1]["jobId"]
        checks.append({"name": "concurrent-atomic-claim", "status": "PASS"})

    engine = create_engine(database_url)
    with engine.connect() as connection:
        counts = {
            "transactions": int(
                connection.scalar(text("SELECT count(*) FROM transaction.transactions")) or 0
            ),
            "manifests": int(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM integration.import_batches "
                        "WHERE contract_version='1.0'"
                    )
                )
                or 0
            ),
            "quarantinedRows": int(
                connection.scalar(text("SELECT count(*) FROM integration.import_rejections")) or 0
            ),
            "catalogEntries": int(
                connection.scalar(text("SELECT count(*) FROM config.transaction_categories")) or 0
            ),
            "receipts": int(
                connection.scalar(text("SELECT count(*) FROM transaction.import_receipts")) or 0
            ),
        }
        lineage_rows = int(
            connection.scalar(
                text(
                    "SELECT count(*) FROM transaction.transactions "
                    "WHERE import_batch_id IS NOT NULL AND source_record_hash IS NOT NULL "
                    "AND category_version IS NOT NULL"
                )
            )
            or 0
        )
    engine.dispose()
    assert counts == {
        "transactions": 5,
        "manifests": 4,
        "quarantinedRows": 1,
        "catalogEntries": 4,
        "receipts": 4,
    }
    assert lineage_rows == 5
    checks.append({"name": "postgres-lineage-and-counts", "status": "PASS"})

    tested_source_files = [
        item for item in os.getenv("INGESTION_TESTED_SOURCE_FILES", "").split(",") if item
    ]
    payload = {
        "schemaVersion": "1.1",
        "runId": f"ingestion-governance-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gitCommit": os.getenv("INGESTION_GIT_COMMIT", "unknown"),
        "sourceRevision": {
            "baseCommit": os.getenv("INGESTION_GIT_COMMIT", "unknown"),
            "worktreeDirty": os.getenv("INGESTION_WORKTREE_DIRTY", "unknown") == "true",
            "testedSourceDigestSha256": os.getenv("INGESTION_TESTED_SOURCE_DIGEST", "unknown"),
            "testedSourceFiles": tested_source_files,
            "digestMethod": "sha256(concatenated sha256sum output in listed order)",
        },
        "scope": {
            "domain": "TRANSACTION",
            "database": "isolated PostgreSQL",
            "dataKind": "DETERMINISTIC_SYNTHETIC_TECHNICAL_FIXTURE",
            "notProved": [
                "BOA source-system integration",
                "BOA data quality or freshness",
                "production throughput, availability or SLO",
                "governed ingestion for Customer, Account and Product domains",
            ],
        },
        "checks": checks,
        "databaseCounts": counts,
        "lineageRows": lineage_rows,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "disclaimer": (
            "Technical evidence on deterministic synthetic data. Freshness is measured without "
            "a BOA-approved threshold. No production, ML-performance or credit-decision claim."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate governed transaction ingestion")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/ingestion/RESULTATS-INGESTION-GOUVERNEE.json"),
    )
    args = parser.parse_args()
    result = asyncio.run(run(args.output))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
