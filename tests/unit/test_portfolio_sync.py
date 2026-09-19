from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.customer_api import _claim_sync_key
from boa_oi.models.entities import (
    AuditLog,
    Customer,
    OutboxMessage,
    PortfolioAssignment,
    PortfolioSyncEvent,
    PortfolioSyncReceipt,
    RelationshipManager,
)
from boa_oi.platform import Principal, Problem, current_principal
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    yield
    application_for("customer-service").dependency_overrides.clear()


def principal(
    role: str,
    *,
    managers: tuple[str, ...] = (),
    client_id: str = "boa-sme-spa",
) -> Principal:
    return Principal(
        subject=f"subject-{role.lower()}",
        username=role.lower(),
        roles={role},
        scopes={"portfolio:sync"} if role == "ADMIN" else set(),
        client_id=client_id,
        relationship_manager_ids=managers,
        branch_ids=(),
        customer_scopes=("global" if role == "ADMIN" else "assigned",),
    )


def context(identity: Principal | None = None):
    identity = identity or principal("ADMIN")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        RelationshipManager.__mapper__.local_table,
        Customer.__mapper__.local_table,
        PortfolioAssignment.__mapper__.local_table,
        PortfolioSyncReceipt.__mapper__.local_table,
        PortfolioSyncEvent.__mapper__.local_table,
        AuditLog.__mapper__.local_table,
        OutboxMessage.__mapper__.local_table,
    ]
    with engine.connect() as connection:
        for schema in ("customer", "audit", "integration"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in tables:
            cast(Table, table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    old_manager = RelationshipManager(
        id=deterministic_uuid("rm", "sync-old"),
        subject_id="rm-sync-old",
        display_name="CC Initial",
        branch_code="BR-01",
        active=True,
    )
    customer = Customer(
        id=deterministic_uuid("customer", "SME-SYNC-001"),
        customer_ref="SME-SYNC-001",
        legal_name="Entreprise Synchronisée",
        sector_code="SERVICES",
        segment_code="SMALL",
        scenario_code="NORMAL_CUSTOMER",
        incorporated_on=date(2019, 1, 1),
        status="ACTIVE",
        rm_id=old_manager.id,
    )
    with factory.begin() as session:
        session.add_all([old_manager, customer])
        session.add(
            PortfolioAssignment(
                id=deterministic_uuid("assignment", "sync-old"),
                customer_id=customer.id,
                relationship_manager_id=old_manager.id,
                branch_code="BR-01",
                portfolio_id="PORTFOLIO-BR-01",
                assignment_type="PRIMARY",
                is_primary=True,
                valid_from=datetime.now(timezone.utc) - timedelta(days=30),
                valid_to=None,
                source_system="SEED",
                source_event_id="seed-sync-old",
                source_payload_hash="0" * 64,
                source_watermark="seed-v1",
                actor="seed",
                reason="Affectation initiale",
            )
        )
    app = application_for("customer-service")
    app.state.session_factory = factory
    app.dependency_overrides[current_principal] = lambda: identity
    return TestClient(app), factory


def payload(
    *,
    event_id: str = "evt-001",
    batch_ref: str = "batch-001",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    portfolio_id: str = "PORTFOLIO-BR-02",
    manager_id: str = "rm-sync-new",
    branch_id: str = "BR-02",
):
    effective = valid_from or datetime.now(timezone.utc)
    return {
        "contractVersion": "1.0",
        "sourceSystem": "CRM_PORTFOLIO",
        "batchRef": batch_ref,
        "sourceWatermark": "2026-09-19T16:00:00Z",
        "assignments": [
            {
                "sourceEventId": event_id,
                "customerId": "SME-SYNC-001",
                "portfolioId": portfolio_id,
                "relationshipManagerId": manager_id,
                "relationshipManagerName": "Nouveau CC",
                "branchId": branch_id,
                "assignmentType": "PRIMARY",
                "isPrimary": True,
                "validFrom": effective.isoformat(),
                "validTo": valid_to.isoformat() if valid_to else None,
                "reason": "Réaffectation pilote validée",
            }
        ],
    }


def test_sync_is_dated_audited_and_replayable(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, factory = context()
    body = payload()

    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-001"},
        json=body,
    )

    assert response.status_code == 202, response.text
    assert response.json()["applied"] == 1
    assert response.json()["replayed"] is False
    with factory() as session:
        assignments = list(
            session.scalars(select(PortfolioAssignment).order_by(PortfolioAssignment.valid_from))
        )
        assert len(assignments) == 2
        assert assignments[0].valid_to is not None
        assert assignments[1].portfolio_id == "PORTFOLIO-BR-02"
        assert assignments[1].source_payload_hash is not None
        assert len(assignments[1].source_payload_hash) == 64
        assert session.scalar(select(func.count()).select_from(PortfolioSyncReceipt)) == 1
        assert session.scalar(select(func.count()).select_from(PortfolioSyncEvent)) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxMessage)) == 1

    replay = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-001"},
        json=body,
    )
    assert replay.status_code == 202
    assert replay.json()["replayed"] is True
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PortfolioAssignment)) == 2
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_same_key_or_source_event_with_different_content_is_rejected(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, _factory = context()
    first = payload()
    assert (
        client.post(
            "/internal/v1/portfolio-assignments/sync",
            headers={"Idempotency-Key": "portfolio-sync-002"},
            json=first,
        ).status_code
        == 202
    )

    changed_batch = payload()
    changed_batch["assignments"][0]["branchId"] = "BR-03"
    conflict = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-002"},
        json=changed_batch,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    changed_event = payload(batch_ref="batch-002")
    changed_event["assignments"][0]["branchId"] = "BR-03"
    event_conflict = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-003"},
        json=changed_event,
    )
    assert event_conflict.status_code == 409
    assert event_conflict.json()["code"] == "SOURCE_EVENT_REUSED"


def test_future_assignment_preserves_current_scope_and_as_of_history(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, factory = context()
    future = datetime.now(timezone.utc) + timedelta(days=7)
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-future"},
        json=payload(event_id="evt-future", batch_ref="batch-future", valid_from=future),
    )
    assert response.status_code == 202, response.text

    current_old = context_for_existing(
        factory, principal("RELATIONSHIP_MANAGER", managers=("rm-sync-old",))
    )
    assert current_old.get("/internal/v1/customers/SME-SYNC-001").status_code == 200
    current_new = context_for_existing(
        factory, principal("RELATIONSHIP_MANAGER", managers=("rm-sync-new",))
    )
    assert current_new.get("/internal/v1/customers/SME-SYNC-001").status_code == 404

    client = context_for_existing(factory, principal("ADMIN"))
    before = client.get(
        "/internal/v1/portfolio-assignments",
        params={"customerId": "SME-SYNC-001", "asOf": (future - timedelta(seconds=1)).isoformat()},
    )
    after = client.get(
        "/internal/v1/portfolio-assignments",
        params={"customerId": "SME-SYNC-001", "asOf": (future + timedelta(seconds=1)).isoformat()},
    )
    assert before.json()["data"][0]["relationshipManagerId"] == "rm-sync-old"
    assert after.json()["data"][0]["relationshipManagerId"] == "rm-sync-new"


def context_for_existing(factory, identity: Principal) -> TestClient:
    app = application_for("customer-service")
    app.state.session_factory = factory
    app.dependency_overrides[current_principal] = lambda: identity
    return TestClient(app)


def test_out_of_order_invalid_timestamp_and_rbac_are_rejected(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, _factory = context()
    backdated = datetime.now(timezone.utc) - timedelta(days=60)
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-old"},
        json=payload(event_id="evt-old", batch_ref="batch-old", valid_from=backdated),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "OUT_OF_ORDER_ASSIGNMENT"

    invalid = payload(event_id="evt-naive", batch_ref="batch-naive")
    invalid["assignments"][0]["validFrom"] = "2026-10-01T10:00:00"
    assert (
        client.post(
            "/internal/v1/portfolio-assignments/sync",
            headers={"Idempotency-Key": "portfolio-sync-naive"},
            json=invalid,
        ).status_code
        == 422
    )

    denied, _factory = context(principal("RELATIONSHIP_MANAGER", managers=("rm-sync-old",)))
    assert (
        denied.post(
            "/internal/v1/portfolio-assignments/sync",
            headers={"Idempotency-Key": "portfolio-sync-denied"},
            json=payload(event_id="evt-denied", batch_ref="batch-denied"),
        ).status_code
        == 403
    )

    authorized_service, _factory = context(
        principal("SERVICE", client_id="banking-integration-service")
    )
    assert (
        authorized_service.post(
            "/internal/v1/portfolio-assignments/sync",
            headers={"Idempotency-Key": "portfolio-sync-service"},
            json=payload(event_id="evt-service", batch_ref="batch-service"),
        ).status_code
        == 202
    )

    unauthorized_service, _factory = context(principal("SERVICE", client_id="action-service"))
    assert (
        unauthorized_service.post(
            "/internal/v1/portfolio-assignments/sync",
            headers={"Idempotency-Key": "portfolio-sync-wrong-service"},
            json=payload(event_id="evt-wrong-service", batch_ref="batch-wrong-service"),
        ).status_code
        == 403
    )


def test_postgresql_claim_conflict_returns_a_controlled_409():
    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class SessionStub:
        def get_bind(self):
            return Bind()

        def scalar(self, _statement):
            return False

    with pytest.raises(Problem) as caught:
        _claim_sync_key(
            SessionStub(),  # type: ignore[arg-type]
            "portfolio-sync-customer",
            "SME-00123",
            code="CUSTOMER_ASSIGNMENT_IN_PROGRESS",
            message="Customer is already being reassigned.",
        )
    assert caught.value.status_code == 409
    assert caught.value.code == "CUSTOMER_ASSIGNMENT_IN_PROGRESS"


def test_historical_interval_requires_reconciliation(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, _factory = context()
    now = datetime.now(timezone.utc)
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-ended"},
        json=payload(
            event_id="evt-ended",
            batch_ref="batch-ended",
            valid_from=now - timedelta(days=10),
            valid_to=now - timedelta(days=1),
        ),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "HISTORICAL_RECONCILIATION_REQUIRED"


def test_same_target_with_different_valid_to_is_rejected_without_mutation(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, factory = context()
    with factory() as session:
        current = session.scalar(select(PortfolioAssignment))
        assert current is not None
        original_valid_from = current.valid_from
        if original_valid_from.tzinfo is None:
            original_valid_from = original_valid_from.replace(tzinfo=timezone.utc)
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-window-conflict"},
        json=payload(
            event_id="evt-window-conflict",
            batch_ref="batch-window-conflict",
            valid_from=original_valid_from,
            valid_to=datetime.now(timezone.utc) + timedelta(days=10),
            portfolio_id="PORTFOLIO-BR-01",
            manager_id="rm-sync-old",
            branch_id="BR-01",
        ),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ASSIGNMENT_INTERVAL_CONFLICT"
    with factory() as session:
        current = session.scalar(select(PortfolioAssignment))
        assert current is not None
        assert current.valid_to is None


def test_same_target_with_different_valid_from_is_rejected(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, factory = context()
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-start-conflict"},
        json=payload(
            event_id="evt-start-conflict",
            batch_ref="batch-start-conflict",
            valid_from=datetime.now(timezone.utc),
            valid_to=None,
            portfolio_id="PORTFOLIO-BR-01",
            manager_id="rm-sync-old",
            branch_id="BR-01",
        ),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ASSIGNMENT_INTERVAL_CONFLICT"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PortfolioAssignment)) == 1


def test_exact_same_target_and_interval_is_recorded_as_no_change(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, factory = context()
    with factory() as session:
        current = session.scalar(select(PortfolioAssignment))
        assert current is not None
        original_valid_from = current.valid_from
        if original_valid_from.tzinfo is None:
            original_valid_from = original_valid_from.replace(tzinfo=timezone.utc)
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-no-change"},
        json=payload(
            event_id="evt-no-change",
            batch_ref="batch-no-change",
            valid_from=original_valid_from,
            portfolio_id="PORTFOLIO-BR-01",
            manager_id="rm-sync-old",
            branch_id="BR-01",
        ),
    )

    assert response.status_code == 202
    assert response.json()["unchanged"] == 1
    assert response.json()["applied"] == 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PortfolioAssignment)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxMessage)) == 0


def test_existing_manager_branch_cannot_be_mutated_by_assignment(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    client, factory = context()
    response = client.post(
        "/internal/v1/portfolio-assignments/sync",
        headers={"Idempotency-Key": "portfolio-sync-manager-conflict"},
        json=payload(
            event_id="evt-manager-conflict",
            batch_ref="batch-manager-conflict",
            manager_id="rm-sync-old",
            branch_id="BR-02",
        ),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "RELATIONSHIP_MANAGER_BRANCH_CONFLICT"
    with factory() as session:
        manager = session.scalar(
            select(RelationshipManager).where(RelationshipManager.subject_id == "rm-sync-old")
        )
        assert manager is not None
        assert manager.branch_code == "BR-01"
