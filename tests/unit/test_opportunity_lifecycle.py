from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from boa_oi import opportunity_api
from boa_oi.models.entities import AuditLog, Opportunity, OpportunityRule
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def opportunity_row(
    *,
    ref: str = "OPP-LIFECYCLE-1",
    status: str = "OPEN",
    expires_at: datetime | None = None,
    cooldown_until: datetime | None = None,
    opportunity_type: str = "INVESTMENT_FINANCING",
) -> Opportunity:
    return Opportunity(
        id=deterministic_uuid("lifecycle-opportunity", ref),
        opportunity_ref=ref,
        customer_id=deterministic_uuid("customer", "SME-00001"),
        customer_ref="SME-00001",
        customer_name="PME Lifecycle",
        opportunity_type=opportunity_type,
        status=status,
        status_updated_at=NOW - timedelta(days=10),
        status_reason="Initial state",
        expires_at=expires_at,
        cooldown_until=cooldown_until,
        horizon="1-3_MONTHS",
        confidence_score=Decimal("0.90"),
        confidence_level="HIGH",
        confidence_components_json=[],
        priority_score=Decimal("90"),
        priority_level="P1",
        priority_components_json=[],
        why_json=[],
        what_text="Proposer un financement",
        when_text="Sous trois mois",
        recommended_products_json=[],
        explanation_json={"evidence": []},
        generated_at=NOW - timedelta(days=10),
        rule_id=deterministic_uuid("lifecycle-rule", "1"),
        deduplication_key=f"lifecycle:{ref}",
    )


@pytest.fixture
def lifecycle_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'opportunity'")
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'audit'")
        cast(Table, OpportunityRule.__mapper__.local_table).create(connection)
        cast(Table, Opportunity.__mapper__.local_table).create(connection)
        cast(Table, AuditLog.__mapper__.local_table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(
            OpportunityRule(
                id=deterministic_uuid("lifecycle-rule", "1"),
                opportunity_type="INVESTMENT_FINANCING",
                version="1",
                configuration_json={"lifecycle": {"dismissed_cooldown_days": 45}},
                active=True,
            )
        )
        session.add(opportunity_row(expires_at=NOW + timedelta(days=10)))

    app = opportunity_api.app
    app.state.session_factory = factory
    with TestClient(app) as client:
        yield client, factory
    del app.state.session_factory
    engine.dispose()


def test_controlled_lifecycle_transitions_and_serializes_timestamps(lifecycle_client) -> None:
    client, _factory = lifecycle_client
    accepted = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={"status": "ACCEPTED", "reason": "Le chargé accepte", "occurredAt": NOW.isoformat()},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    assert accepted.json()["statusUpdatedAt"] == NOW.isoformat()
    assert accepted.json()["lastActionAt"] == NOW.isoformat()

    contacted_at = NOW + timedelta(hours=1)
    contacted = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "CONTACTED",
            "reason": "Client joint",
            "occurredAt": contacted_at.isoformat(),
        },
    )
    assert contacted.status_code == 200, contacted.text
    assert contacted.json()["status"] == "CONTACTED"

    converted_at = NOW + timedelta(hours=2)
    converted = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "CONVERTED",
            "reason": "Produit souscrit",
            "occurredAt": converted_at.isoformat(),
        },
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["status"] == "CONVERTED"
    assert (
        converted.json()["cooldownUntil"]
        == (
            converted_at
            + timedelta(days=opportunity_api.lifecycle_policy({})["converted_cooldown_days"])
        ).isoformat()
    )
    with _factory() as session:
        audit = session.scalar(
            select(AuditLog)
            .where(AuditLog.action == "OPPORTUNITY_CONVERTED")
            .order_by(AuditLog.occurred_at.desc())
        )
        assert audit is not None
        assert audit.metadata_json["before"]["status"] == "CONTACTED"
        assert audit.metadata_json["after"]["status"] == "CONVERTED"

    replay = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "CONVERTED",
            "reason": "Rejeu de récupération interservice",
            "occurredAt": (converted_at + timedelta(minutes=1)).isoformat(),
        },
    )
    assert replay.status_code == 200
    assert datetime.fromisoformat(replay.json()["cooldownUntil"]).replace(
        tzinfo=timezone.utc
    ) == datetime.fromisoformat(converted.json()["cooldownUntil"])

    conflicting_replay = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "CONVERTED",
            "reason": "Rejeu contradictoire",
            "occurredAt": (converted_at + timedelta(minutes=2)).isoformat(),
            "cooldownUntil": (converted_at + timedelta(days=10)).isoformat(),
        },
    )
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["code"] == "OPPORTUNITY_TRANSITION_REPLAY_CONFLICT"

    reopened = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "OPEN",
            "reason": "Réouverture interdite",
            "occurredAt": (converted_at + timedelta(minutes=3)).isoformat(),
        },
    )
    assert reopened.status_code == 409
    assert reopened.json()["code"] == "INVALID_OPPORTUNITY_TRANSITION"


def test_maintenance_expires_only_due_active_opportunities(lifecycle_client) -> None:
    client, factory = lifecycle_client
    with factory.begin() as session:
        due = opportunity_row(ref="OPP-DUE", status="ACCEPTED", expires_at=NOW - timedelta(days=1))
        future = opportunity_row(ref="OPP-FUTURE", expires_at=NOW + timedelta(days=1))
        terminal = opportunity_row(ref="OPP-DISMISSED", status="DISMISSED", expires_at=NOW)
        session.add_all([due, future, terminal])

    response = client.post(
        "/internal/v1/opportunities/maintenance/expire",
        json={"asOf": NOW.isoformat(), "reason": "Échéance de validité"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["expired"] == 1
    with factory() as session:
        statuses = {
            item.opportunity_ref: item.status for item in session.scalars(select(Opportunity)).all()
        }
    assert statuses["OPP-DUE"] == "EXPIRED"
    assert statuses["OPP-FUTURE"] == "OPEN"
    assert statuses["OPP-DISMISSED"] == "DISMISSED"
    with factory() as session:
        due = session.scalar(select(Opportunity).where(Opportunity.opportunity_ref == "OPP-DUE"))
        assert due is not None
        assert due.last_action_at is None


def test_transition_command_is_idempotent_and_keeps_commercial_actor(lifecycle_client) -> None:
    client, factory = lifecycle_client
    payload = {
        "status": "DEFERRED",
        "reason": "À revoir après campagne",
        "occurredAt": NOW.isoformat(),
        "cooldownUntil": (NOW + timedelta(days=30)).isoformat(),
        "actorSubjectId": "rm-commercial-01",
    }
    headers = {"Idempotency-Key": "action-command-defer-001"}

    first = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        headers=headers,
        json=payload,
    )
    replay = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        headers=headers,
        json=payload,
    )
    conflict = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        headers=headers,
        json={**payload, "reason": "Contenu différent"},
    )

    assert first.status_code == replay.status_code == 200
    assert replay.json()["status"] == "DEFERRED"
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    with factory() as session:
        audits = list(
            session.scalars(select(AuditLog).where(AuditLog.action == "OPPORTUNITY_DEFERRED"))
        )
        assert len(audits) == 1
        assert audits[0].actor_subject_id == "rm-commercial-01"
        assert audits[0].metadata_json["authorizedBy"] == "local-test-user"


def test_generation_claim_uses_advisory_and_row_locks() -> None:
    statements: list[Any] = []

    class Bind:
        class dialect:
            name = "postgresql"

    class SessionDouble:
        def get_bind(self) -> Bind:
            return Bind()

        def scalar(self, statement: Any) -> bool | None:
            statements.append(statement)
            rendered = str(statement.compile(dialect=postgresql.dialect()))
            if "pg_try_advisory_xact_lock" in rendered:
                return True
            return None

    decision, terminal, active = opportunity_api.classify_generation(
        cast(Any, SessionDouble()),
        customer_id=deterministic_uuid("customer", "SME-LOCK"),
        opportunity_type="INVESTMENT_FINANCING",
        as_of=NOW,
    )

    rendered = [str(statement.compile(dialect=postgresql.dialect())) for statement in statements]
    assert decision == "CREATED"
    assert terminal is active is None
    assert "pg_try_advisory_xact_lock" in rendered[0]
    assert all("FOR UPDATE" in statement for statement in rendered[1:])


def test_expiration_claim_uses_skip_locked() -> None:
    statements: list[Any] = []

    class SessionDouble:
        def scalars(self, statement: Any) -> list[Any]:
            statements.append(statement)
            return []

    expired = opportunity_api.expire_due_opportunities(
        cast(Any, SessionDouble()),
        as_of=NOW,
    )

    rendered = str(statements[0].compile(dialect=postgresql.dialect()))
    assert expired == 0
    assert "FOR UPDATE SKIP LOCKED" in rendered


def test_generation_claim_conflict_is_controlled() -> None:
    class Bind:
        class dialect:
            name = "postgresql"

    class SessionDouble:
        def get_bind(self) -> Bind:
            return Bind()

        def scalar(self, statement: Any) -> bool:
            del statement
            return False

    with pytest.raises(opportunity_api.Problem) as captured:
        opportunity_api.classify_generation(
            cast(Any, SessionDouble()),
            customer_id=deterministic_uuid("customer", "SME-LOCKED"),
            opportunity_type="INVESTMENT_FINANCING",
            as_of=NOW,
        )

    assert captured.value.status_code == 409
    assert captured.value.code == "GENERATION_IN_PROGRESS"


def test_batch_claim_deduplicates_customers_before_generation() -> None:
    statements: list[Any] = []

    class Bind:
        class dialect:
            name = "postgresql"

    class SessionDouble:
        def get_bind(self) -> Bind:
            return Bind()

        def scalar(self, statement: Any) -> bool:
            statements.append(statement)
            return True

    opportunity_api.claim_generation_customers(
        cast(Any, SessionDouble()),
        ["SME-00002", "SME-00001", "SME-00002"],
    )

    assert len(statements) == 2
    assert all(
        "pg_try_advisory_xact_lock" in str(statement.compile(dialect=postgresql.dialect()))
        for statement in statements
    )


def test_deferred_transition_uses_requested_review_date(lifecycle_client) -> None:
    client, _factory = lifecycle_client
    review_at = NOW + timedelta(days=45)

    response = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "DEFERRED",
            "reason": "À revoir après la campagne",
            "occurredAt": NOW.isoformat(),
            "cooldownUntil": review_at.isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DEFERRED"
    assert response.json()["cooldownUntil"] == review_at.isoformat()


def test_dismissed_transition_uses_rule_specific_cooldown(lifecycle_client) -> None:
    client, _factory = lifecycle_client

    response = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "DISMISSED",
            "reason": "Non pertinent",
            "occurredAt": NOW.isoformat(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["cooldownUntil"] == (NOW + timedelta(days=45)).isoformat()


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/internal/v1/opportunities?fromDate=not-a-date", "VALIDATION_ERROR"),
        ("/internal/v1/opportunities?minConfidence=NaN", "VALIDATION_ERROR"),
        (
            "/internal/v1/opportunities?fromDate=2026-09-30&toDate=2026-09-30",
            "VALIDATION_ERROR",
        ),
    ],
)
def test_invalid_filters_return_422(lifecycle_client, path: str, code: str) -> None:
    client, _factory = lifecycle_client

    response = client.get(path)

    assert response.status_code == 422
    assert response.json()["code"] == code


def test_invalid_lifecycle_jump_returns_409_without_audit(lifecycle_client) -> None:
    client, factory = lifecycle_client

    response = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "CONVERTED",
            "reason": "Transition directe interdite",
            "occurredAt": NOW.isoformat(),
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_OPPORTUNITY_TRANSITION"
    with factory() as session:
        assert session.scalar(select(AuditLog)) is None


def test_lifecycle_rejects_naive_timestamp_and_invalid_cooldown(lifecycle_client) -> None:
    client, _factory = lifecycle_client

    naive = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "DISMISSED",
            "reason": "Horodatage sans fuseau",
            "occurredAt": "2026-09-30T10:00:00",
        },
    )
    assert naive.status_code == 422
    assert naive.json()["code"] == "VALIDATION_ERROR"

    invalid_cooldown = client.post(
        "/internal/v1/opportunities/OPP-LIFECYCLE-1/transition",
        json={
            "status": "DISMISSED",
            "reason": "Cooldown antérieur",
            "occurredAt": NOW.isoformat(),
            "cooldownUntil": (NOW - timedelta(days=1)).isoformat(),
        },
    )
    assert invalid_cooldown.status_code == 422
    assert invalid_cooldown.json()["code"] == "VALIDATION_ERROR"


def test_generation_decision_classifies_create_refresh_and_cooldown_suppression(
    lifecycle_client,
) -> None:
    _client, factory = lifecycle_client
    customer_id = deterministic_uuid("customer", "SME-00001")
    with factory() as session:
        decision, terminal_match, active_match = opportunity_api.classify_generation(
            session,
            customer_id=customer_id,
            opportunity_type="INVESTMENT_FINANCING",
            as_of=NOW,
        )
        assert decision == "REFRESHED"
        assert terminal_match is None
        assert active_match is not None

    with factory.begin() as session:
        session.add(
            opportunity_row(
                ref="OPP-TERMINAL",
                status="DISMISSED",
                expires_at=NOW - timedelta(days=5),
                cooldown_until=NOW + timedelta(days=5),
            )
        )
    with factory() as session:
        decision, terminal_match, active_match = opportunity_api.classify_generation(
            session,
            customer_id=customer_id,
            opportunity_type="INVESTMENT_FINANCING",
            as_of=NOW,
        )
        assert decision == "SUPPRESSED"
        assert terminal_match is not None
        assert active_match is not None

        decision, terminal_match, active_match = opportunity_api.classify_generation(
            session,
            customer_id=deterministic_uuid("customer", "SME-UNKNOWN"),
            opportunity_type="INVESTMENT_FINANCING",
            as_of=NOW,
        )
        assert (decision, terminal_match, active_match) == ("CREATED", None, None)


def test_expire_due_function_updates_counter_exactly() -> None:
    engine = create_engine("sqlite+pysqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'opportunity'")
        cast(Table, OpportunityRule.__mapper__.local_table).create(connection)
        cast(Table, Opportunity.__mapper__.local_table).create(connection)
        factory = sessionmaker(bind=connection, expire_on_commit=False)
        with factory.begin() as session:
            session.add(
                OpportunityRule(
                    id=deterministic_uuid("lifecycle-rule", "1"),
                    opportunity_type="INVESTMENT_FINANCING",
                    version="1",
                    configuration_json={},
                    active=True,
                )
            )
            session.add_all(
                [
                    opportunity_row(ref="OPP-ONE", expires_at=NOW - timedelta(seconds=1)),
                    opportunity_row(ref="OPP-TWO", expires_at=NOW),
                    opportunity_row(ref="OPP-THREE", expires_at=NOW + timedelta(seconds=1)),
                ]
            )
        with factory.begin() as session:
            assert opportunity_api.expire_due_opportunities(session, as_of=NOW) == 2
        with factory() as session:
            opportunity = session.scalar(
                select(Opportunity).where(Opportunity.opportunity_ref == "OPP-ONE")
            )
            assert opportunity is not None
            cooldown = opportunity.cooldown_until
            assert cooldown is not None
            assert cooldown.replace(tzinfo=timezone.utc) == NOW + timedelta(
                days=opportunity_api.lifecycle_policy({})["expired_cooldown_days"]
            )
    engine.dispose()


def test_low_visibility_expires_active_cash_opportunity_with_audit(
    lifecycle_client,
) -> None:
    _client, factory = lifecycle_client
    with factory.begin() as session:
        session.add(
            opportunity_row(
                ref="OPP-CASH-LOW",
                expires_at=NOW + timedelta(days=30),
                opportunity_type="CASH_INVESTMENT",
            )
        )
    with factory.begin() as session:
        suppressed = opportunity_api.suppress_low_visibility_cash_opportunities(
            session,
            customer_ref="SME-00001",
            visibility_level="LOW",
            as_of=NOW,
            actor_subject_id="pipeline-test",
            audit_correlation="visibility-low-test",
        )
        assert suppressed == 1
    with factory() as session:
        opportunity = session.scalar(
            select(Opportunity).where(Opportunity.opportunity_ref == "OPP-CASH-LOW")
        )
        assert opportunity is not None
        assert opportunity.status == "EXPIRED"
        assert opportunity.status_reason == "Placement retiré : visibilité des flux faible"
        audit = session.scalar(
            select(AuditLog).where(
                AuditLog.resource_id == "OPP-CASH-LOW",
                AuditLog.action == "OPPORTUNITY_EXPIRED_LOW_VISIBILITY",
            )
        )
        assert audit is not None
        assert audit.correlation_id == "visibility-low-test"


__all__ = ["opportunity_row"]
