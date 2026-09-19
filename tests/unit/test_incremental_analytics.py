from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from boa_oi import analytics_api
from boa_oi.analytics.domain import BalanceFact, TransactionFact
from boa_oi.models.entities import ImportBatch
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def analytics_client(
    monkeypatch,
) -> Iterator[tuple[TestClient, sessionmaker[Session], dict[str, Decimal], list[str]]]:
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'integration'")
        cast(Table, ImportBatch.__mapper__.local_table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    amounts = {
        "SME-00001": Decimal("100.00"),
        "SME-00002": Decimal("200.00"),
    }
    persisted: list[str] = []

    async def fake_load(customer_id, as_of, request):
        del request
        return analytics_api.AnalyticsInputs(
            transactions=(
                TransactionFact(
                    transaction_ref=f"tx-{customer_id}",
                    customer_id=customer_id,
                    account_id=f"account-{customer_id}",
                    value_date=as_of,
                    direction="CREDIT",
                    amount=amounts[customer_id],
                    category="TRANSFER",
                ),
            ),
            balances=(
                BalanceFact(
                    account_id=f"account-{customer_id}",
                    as_of_date=as_of,
                    closing_balance=Decimal("1000.00"),
                ),
            ),
        )

    def fake_persist(customer_id, as_of, periods, inputs, input_hash, session):
        del as_of, inputs, input_hash, session
        persisted.append(customer_id)
        return len(periods) * 3

    monkeypatch.setattr(analytics_api, "load_analytics_inputs", fake_load)
    monkeypatch.setattr(analytics_api, "persist_analytics_metrics", fake_persist)
    analytics_api.app.state.session_factory = factory
    try:
        with TestClient(analytics_api.app) as client:
            yield client, factory, amounts, persisted
    finally:
        analytics_api.app.state.session_factory = None
        analytics_api.app.dependency_overrides.clear()
        engine.dispose()


def post_recompute(client: TestClient, payload: Mapping[str, object], key: str):
    return client.post(
        "/internal/v1/analytics/recompute",
        json=payload,
        headers={"Idempotency-Key": key},
    )


def test_incremental_customer_checkpoints_process_then_skip_unchanged_inputs(analytics_client):
    client, factory, amounts, persisted = analytics_client
    payload = {
        "customerIds": ["SME-00001", "SME-00002"],
        "asOf": "2026-09-30",
        "periods": ["30D"],
        "mode": "INCREMENTAL",
        "checkpointScope": "CUSTOMER",
    }

    first = post_recompute(client, payload, "customer-run-0001")
    assert first.status_code == 202, first.text
    assert {
        field: first.json()[field]
        for field in ("processed", "skipped", "metrics", "mode", "checkpointScope")
    } == {
        "processed": 2,
        "skipped": 0,
        "metrics": 6,
        "mode": "INCREMENTAL",
        "checkpointScope": "CUSTOMER",
    }
    assert first.json()["lastEvaluatedAt"]
    assert persisted == ["SME-00001", "SME-00002"]

    second = post_recompute(client, payload, "customer-run-0002")
    assert second.status_code == 202, second.text
    assert second.json()["processed"] == 0
    assert second.json()["skipped"] == 2
    assert second.json()["metrics"] == 0
    assert persisted == ["SME-00001", "SME-00002"]

    amounts["SME-00001"] = Decimal("101.00")
    third = post_recompute(client, payload, "customer-run-0003")
    assert third.status_code == 202, third.text
    assert third.json()["processed"] == 1
    assert third.json()["skipped"] == 1
    assert third.json()["metrics"] == 3
    assert persisted == ["SME-00001", "SME-00002", "SME-00001"]

    with factory() as session:
        checkpoints = list(
            session.scalars(
                select(ImportBatch).where(
                    ImportBatch.source_system == analytics_api.CHECKPOINT_SOURCE
                )
            )
        )
    assert len(checkpoints) == 2
    assert all(item.completed_at is not None for item in checkpoints)
    assert all(len(item.input_hash) == 64 for item in checkpoints)


def test_incremental_batch_checkpoint_reprocesses_the_whole_batch_on_change(analytics_client):
    client, factory, amounts, persisted = analytics_client
    payload = {
        "customerIds": ["SME-00001", "SME-00002"],
        "asOf": "2026-09-30",
        "periods": ["30D", "90D"],
        "mode": "INCREMENTAL",
        "checkpointScope": "BATCH",
        "checkpointKey": "nightly-portfolio",
    }

    first = post_recompute(client, payload, "batch-run-0001")
    assert first.status_code == 202, first.text
    assert first.json()["processed"] == 2
    assert first.json()["skipped"] == 0
    assert first.json()["metrics"] == 12

    second = post_recompute(client, payload, "batch-run-0002")
    assert second.status_code == 202, second.text
    assert second.json()["processed"] == 0
    assert second.json()["skipped"] == 2
    assert second.json()["metrics"] == 0

    amounts["SME-00001"] = Decimal("101.00")
    third = post_recompute(client, payload, "batch-run-0003")
    assert third.status_code == 202, third.text
    assert third.json()["processed"] == 2
    assert third.json()["skipped"] == 0
    assert third.json()["metrics"] == 12
    assert persisted == [
        "SME-00001",
        "SME-00002",
        "SME-00001",
        "SME-00002",
    ]

    with factory() as session:
        checkpoints = list(
            session.scalars(
                select(ImportBatch).where(
                    ImportBatch.source_system == analytics_api.CHECKPOINT_SOURCE
                )
            )
        )
    assert len(checkpoints) == 1
    assert checkpoints[0].row_count == 12


def test_explicit_historical_mode_always_recomputes_without_checkpoint(analytics_client):
    client, factory, _amounts, persisted = analytics_client
    payload = {
        "customerIds": ["SME-00001"],
        "asOf": date(2026, 9, 30).isoformat(),
        "periods": ["30D"],
        "mode": "HISTORICAL",
    }

    first = post_recompute(client, payload, "history-run-0001")
    second = post_recompute(client, payload, "history-run-0002")
    for response in (first, second):
        assert response.status_code == 202, response.text
        assert response.json()["processed"] == 1
        assert response.json()["skipped"] == 0
        assert response.json()["metrics"] == 3
        assert response.json()["mode"] == "HISTORICAL"
    assert persisted == ["SME-00001", "SME-00001"]

    with factory() as session:
        assert session.scalar(select(ImportBatch)) is None


def test_recompute_contract_exposes_incremental_modes_and_counters():
    openapi = analytics_api.app.openapi()
    operation = openapi["paths"]["/internal/v1/analytics/recompute"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    schema_name = request_schema["$ref"].rsplit("/", 1)[-1]
    schema = openapi["components"]["schemas"][schema_name]

    assert schema["properties"]["mode"]["enum"] == ["INCREMENTAL", "HISTORICAL"]
    assert schema["properties"]["mode"]["default"] == "INCREMENTAL"
    assert schema["properties"]["checkpointScope"]["enum"] == ["CUSTOMER", "BATCH"]
    assert schema["properties"]["checkpointScope"]["default"] == "CUSTOMER"
    response_schema = operation["responses"]["202"]["content"]["application/json"]["schema"]
    response_name = response_schema["$ref"].rsplit("/", 1)[-1]
    response_properties = openapi["components"]["schemas"][response_name]["properties"]
    assert {"processed", "skipped", "lastEvaluatedAt"} <= set(response_properties)
