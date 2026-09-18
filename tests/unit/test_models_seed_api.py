from boa_oi.api import app
from boa_oi.models import Base
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient

from database.seed.generate import (
    CUSTOMER_COUNT,
    END_DATE,
    MIN_TRANSACTIONS,
    SCENARIOS,
    START_DATE,
    generate_transaction_rows,
    manifest,
    scenario_for,
)


def test_model_contains_all_required_domain_tables_and_schemas():
    required = {
        "customers",
        "relationship_managers",
        "accounts",
        "credit_lines",
        "account_balances",
        "transactions",
        "products",
        "customer_products",
        "metric_snapshots",
        "signal_rules",
        "signals",
        "opportunity_rules",
        "opportunities",
        "opportunity_evidence",
        "opportunity_actions",
        "audit_logs",
        "rule_configurations",
        "outbox_messages",
    }
    assert required <= {table.name for table in Base.metadata.tables.values()}
    schemas = {table.schema for table in Base.metadata.tables.values()}
    assert {
        "customer",
        "account",
        "transaction",
        "product",
        "analytics",
        "signal",
        "opportunity",
        "action",
        "audit",
        "config",
        "integration",
    } <= schemas


def test_transaction_indexes_and_uniqueness_present():
    table = Base.metadata.tables["transaction.transactions"]
    index_columns = {tuple(column.name for column in index.columns) for index in table.indexes}
    assert ("customer_id", "value_date") in index_columns and (
        "account_id",
        "value_date",
    ) in index_columns
    assert any(
        {column.name for column in constraint.columns} == {"source_system", "transaction_ref"}
        for constraint in table.constraints
        if hasattr(constraint, "columns")
    )


def test_seed_manifest_contract_and_scenario_coverage():
    data = manifest()
    assert (
        data["customers"] == 500 == CUSTOMER_COUNT
        and data["minimum_transactions"] >= 300000 == MIN_TRANSACTIONS
    )
    assert len(data["sectors"]) == 8 and set(data["scenarios"]) == set(SCENARIOS)
    assert data["opportunities"] == 0 and (END_DATE - START_DATE).days >= 364
    assert {scenario_for(i) for i in range(1, 501)} == set(SCENARIOS)


def test_generated_transactions_are_deterministic_coherent_and_dense():
    customer_id = deterministic_uuid("customer", "SME-00001")
    account_id = deterministic_uuid("account", "SME-00001", 1)
    first = list(generate_transaction_rows(1, customer_id, account_id))
    second = list(generate_transaction_rows(1, customer_id, account_id))
    assert first == second and len(first) >= 365
    assert all(
        row["amount"] > 0
        and START_DATE <= row["value_date"] <= END_DATE
        and row["customer_id"] == customer_id
        for row in first
    )
    projected = sum(
        len(
            list(
                generate_transaction_rows(i, deterministic_uuid("c", i), deterministic_uuid("a", i))
            )
        )
        for i in range(1, 501)
    )
    assert projected >= MIN_TRANSACTIONS


def test_api_operations_openapi_and_correlation():
    client = TestClient(app)
    response = client.get("/health", headers={"X-Correlation-ID": "corr-test"})
    assert response.status_code == 200 and response.headers["X-Correlation-ID"] == "corr-test"
    assert client.get("/ready").json()["status"] == "ready"
    assert "boa_service_info" in client.get("/metrics").text
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.") and "/health" in spec["paths"]
