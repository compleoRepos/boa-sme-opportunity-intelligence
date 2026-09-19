from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from boa_oi import action_api
from boa_oi.api import application_for
from boa_oi.models.entities import ActionOutcome, AuditLog, OpportunityAction
from boa_oi.platform import Principal, current_principal
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def action_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, sessionmaker]]:
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        for schema in ("action", "audit"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in (
            OpportunityAction.__mapper__.local_table,
            ActionOutcome.__mapper__.local_table,
            AuditLog.__mapper__.local_table,
        ):
            cast(Table, table).create(connection)

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    principal = Principal(
        subject="rm-action-test",
        username="rm.action.test",
        roles={"RELATIONSHIP_MANAGER"},
        scopes=set(),
        client_id="boa-sme-spa",
        relationship_manager_ids=("rm-action-test",),
        branch_ids=("BR-01",),
        customer_scopes=("assigned",),
    )
    app = application_for("action-service")
    app.state.session_factory = factory
    app.dependency_overrides[current_principal] = lambda: principal

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def fake_service_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, url, kwargs.get("json")))
        if method == "GET":
            return {"opportunityId": "OPP-001", "customerId": "SME-00001", "status": "OPEN"}
        if app.state.transition_failures_remaining:
            app.state.transition_failures_remaining -= 1
            raise action_api.Problem(503, "DEPENDENCY_UNAVAILABLE", "simulated failure")
        return {"status": "UPDATED"}

    monkeypatch.setattr(action_api, "service_request", fake_service_request)
    monkeypatch.setattr(action_api, "opportunity_url", lambda: "http://opportunity")
    monkeypatch.setattr(action_api, "customer_url", lambda: "http://customer")
    app.state.test_transition_calls = calls
    app.state.transition_failures_remaining = 0

    with TestClient(app) as client:
        yield client, factory

    app.dependency_overrides.clear()
    del app.state.session_factory
    del app.state.test_transition_calls
    del app.state.transition_failures_remaining
    engine.dispose()


def _seed_action(
    factory: sessionmaker,
    *,
    status: str,
    outcome: str | None = None,
    action_type: str = "CONTACT_CUSTOMER",
) -> str:
    action_ref = "ACTION-001"
    with factory.begin() as session:
        session.add(
            OpportunityAction(
                id=deterministic_uuid("action-test", action_ref),
                action_ref=action_ref,
                opportunity_id=deterministic_uuid("opportunity-row", "OPP-001"),
                opportunity_ref="OPP-001",
                customer_id=deterministic_uuid("customer", "SME-00001"),
                customer_ref="SME-00001",
                action_type=action_type,
                status=status,
                actor_subject_id="rm-action-test",
                assigned_to="rm.action.test",
                scheduled_at=None,
                due_at=None,
                performed_at=datetime.now(timezone.utc) if status == "COMPLETED" else None,
                notes_redacted=None,
                outcome_type=outcome,
                idempotency_key=f"idem-{status}-{outcome}",
                request_hash="hash",
                correlation_id="seed",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    return action_ref


def test_create_action_transitions_opportunity_and_writes_audit(action_context):
    client, factory = action_context

    response = client.post(
        "/internal/v1/actions",
        headers={"Idempotency-Key": "accept-opportunity-001"},
        json={
            "opportunityId": "OPP-001",
            "customerId": "SME-00001",
            "actionType": "ACCEPT_OPPORTUNITY",
            "note": "Acceptée pour contact",
        },
    )

    assert response.status_code == 201
    calls = client.app.state.test_transition_calls
    assert calls[-1][2] == {
        "status": "ACCEPTED",
        "reason": "Commercial action ACCEPT_OPPORTUNITY by rm-action-test",
        "actorSubjectId": "rm-action-test",
    }
    with factory() as session:
        audit = session.scalar(select(AuditLog).where(AuditLog.action == "ACTION_CREATED"))
        assert audit is not None
        assert audit.metadata_json["before"] is None
        assert audit.metadata_json["after"]["status"] == "IN_PROGRESS"
        applied = session.scalar(
            select(AuditLog).where(AuditLog.action == "OPPORTUNITY_TRANSITION_APPLIED")
        )
        assert applied is not None
        assert applied.metadata_json["after"]["status"] == "COMPLETED"


def test_defer_action_sets_review_cooldown_and_structured_outcome(action_context):
    client, factory = action_context
    review_at = "2030-10-30T09:00:00Z"

    response = client.post(
        "/internal/v1/actions",
        headers={"Idempotency-Key": "defer-opportunity-001"},
        json={
            "opportunityId": "OPP-001",
            "customerId": "SME-00001",
            "actionType": "DEFER_OPPORTUNITY",
            "dueAt": review_at,
            "note": "Revoir après la campagne annuelle",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["outcome"] == "REVIEW_LATER"
    calls = client.app.state.test_transition_calls
    assert calls[-1][1].endswith("/OPP-001/transition")
    assert calls[-1][2] == {
        "status": "DEFERRED",
        "reason": "Commercial action DEFER_OPPORTUNITY by rm-action-test",
        "actorSubjectId": "rm-action-test",
        "cooldownUntil": "2030-10-30T09:00:00+00:00",
    }
    with factory() as session:
        outcome = session.scalar(
            select(ActionOutcome).where(ActionOutcome.outcome_type == "REVIEW_LATER")
        )
        assert outcome is not None


def test_invalid_action_transition_is_rejected(action_context):
    client, factory = action_context
    action_ref = _seed_action(factory, status="COMPLETED", outcome="CONTACTED")

    response = client.patch(
        f"/internal/v1/actions/{action_ref}",
        json={"status": "OPEN"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_ACTION_TRANSITION"


def test_duplicate_terminal_action_is_rejected_with_new_idempotency_key(action_context):
    client, factory = action_context
    _seed_action(factory, status="COMPLETED", action_type="ACCEPT_OPPORTUNITY")

    response = client.post(
        "/internal/v1/actions",
        headers={"Idempotency-Key": "second-accept-attempt"},
        json={
            "opportunityId": "OPP-001",
            "customerId": "SME-00001",
            "actionType": "ACCEPT_OPPORTUNITY",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_ACTION"
    assert client.app.state.test_transition_calls == [
        ("GET", "http://opportunity/internal/v1/opportunities/OPP-001", None)
    ]


def test_repeated_outcome_is_idempotent_and_not_duplicated(action_context):
    client, factory = action_context
    action_ref = _seed_action(factory, status="COMPLETED", outcome="CONTACTED")
    with factory.begin() as session:
        action = session.scalar(
            select(OpportunityAction).where(OpportunityAction.action_ref == action_ref)
        )
        assert action is not None
        session.add(
            ActionOutcome(
                id=deterministic_uuid("outcome", action_ref, "CONTACTED"),
                action_id=action.id,
                outcome_type="CONTACTED",
                recorded_by="rm-action-test",
                correlation_id="seed",
                metadata_json={"source": "seed"},
            )
        )

    response = client.patch(
        f"/internal/v1/actions/{action_ref}",
        json={"outcome": "CONTACTED"},
    )

    assert response.status_code == 200
    with factory() as session:
        count = session.scalar(select(func.count()).select_from(ActionOutcome))
        assert count == 1
    assert client.app.state.test_transition_calls == [
        ("GET", "http://opportunity/internal/v1/opportunities/OPP-001", None)
    ]


def test_terminal_outcome_cannot_be_replaced(action_context):
    client, factory = action_context
    action_ref = _seed_action(factory, status="COMPLETED", outcome="CONTACTED")

    response = client.patch(
        f"/internal/v1/actions/{action_ref}",
        json={"outcome": "CONVERTED"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "OUTCOME_CONFLICT"


def test_failed_transition_is_durable_and_resumed_with_same_key(action_context):
    client, factory = action_context
    client.app.state.transition_failures_remaining = 1
    payload = {
        "opportunityId": "OPP-001",
        "customerId": "SME-00001",
        "actionType": "ACCEPT_OPPORTUNITY",
        "note": "Commande durable",
    }

    failed = client.post(
        "/internal/v1/actions",
        headers={"Idempotency-Key": "durable-transition-001"},
        json=payload,
    )

    assert failed.status_code == 503
    with factory() as session:
        pending = session.scalar(
            select(OpportunityAction).where(
                OpportunityAction.idempotency_key == "durable-transition-001"
            )
        )
        assert pending is not None
        assert pending.status == "IN_PROGRESS"
        assert pending.transition_status == "FAILED"
        assert pending.transition_target == "ACCEPTED"
        assert pending.transition_attempt_count == 1
        assert pending.transition_error == "DEPENDENCY_UNAVAILABLE"

    resumed = client.post(
        "/internal/v1/actions",
        headers={"Idempotency-Key": "durable-transition-001"},
        json=payload,
    )

    assert resumed.status_code == 201, resumed.text
    assert resumed.json()["status"] == "COMPLETED"
    assert resumed.json()["transitionStatus"] == "APPLIED"
    with factory() as session:
        completed = session.scalar(
            select(OpportunityAction).where(
                OpportunityAction.idempotency_key == "durable-transition-001"
            )
        )
        assert completed is not None
        assert completed.transition_attempt_count == 2
        events = set(session.scalars(select(AuditLog.action)).all())
        assert "OPPORTUNITY_TRANSITION_FAILED" in events
        assert "OPPORTUNITY_TRANSITION_APPLIED" in events


def test_planned_contact_does_not_mark_opportunity_contacted(action_context):
    client, _factory = action_context

    response = client.post(
        "/internal/v1/actions",
        headers={"Idempotency-Key": "planned-contact-001"},
        json={
            "opportunityId": "OPP-001",
            "customerId": "SME-00001",
            "actionType": "CONTACT_CUSTOMER",
            "dueAt": "2030-10-30T09:00:00Z",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "OPEN"
    assert response.json()["transitionStatus"] == "NOT_REQUIRED"
    assert client.app.state.test_transition_calls == [
        ("GET", "http://opportunity/internal/v1/opportunities/OPP-001", None)
    ]


def test_update_and_filtered_list_require_remote_object_scope(action_context, monkeypatch):
    client, factory = action_context
    action_ref = _seed_action(factory, status="OPEN")

    async def reject_scope(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        del method, url, kwargs
        raise action_api.Problem(404, "RESOURCE_NOT_FOUND", "Resource was not found.")

    monkeypatch.setattr(action_api, "service_request", reject_scope)

    update = client.patch(
        f"/internal/v1/actions/{action_ref}",
        json={"status": "IN_PROGRESS"},
    )
    filtered = client.get("/internal/v1/customers/SME-00001/actions")

    assert update.status_code == 404
    assert filtered.status_code == 404
    with factory() as session:
        unchanged = session.scalar(
            select(OpportunityAction).where(OpportunityAction.action_ref == action_ref)
        )
        assert unchanged is not None
        assert unchanged.status == "OPEN"
