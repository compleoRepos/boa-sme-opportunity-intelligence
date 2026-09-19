from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from boa_oi import notification_api
from boa_oi.api import application_for
from boa_oi.models.entities import (
    NotificationDeliveryAttempt,
    NotificationDigestSubscription,
    NotificationMessage,
    OutboxMessage,
)
from boa_oi.platform import Principal, current_principal
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        for schema in ("integration", "notification"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in (
            OutboxMessage.__mapper__.local_table,
            NotificationMessage.__mapper__.local_table,
            NotificationDigestSubscription.__mapper__.local_table,
            NotificationDeliveryAttempt.__mapper__.local_table,
        ):
            cast(Table, table).create(connection)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_event(session_factory, *, event_ref: str = "event-001") -> None:
    with session_factory.begin() as session:
        session.add(
            OutboxMessage(
                id=deterministic_uuid("event", event_ref),
                event_type="ACTION_NOTIFICATION_REQUESTED",
                aggregate_type="OPPORTUNITY_ACTION",
                aggregate_id="ACTION-001",
                payload_json={
                    "actionType": "CONTACT_CUSTOMER",
                    "opportunityId": "OPP-001<script>",
                    "dueAt": "2030-10-30T09:00:00+00:00",
                    "recipientEmail": "rm.test@synthetic.invalid",
                    "recipientName": "rm.test",
                },
                correlation_id="corr-notification",
                causation_id="idem-action",
                occurred_at=datetime.now(timezone.utc),
                attempt_count=0,
            )
        )


def test_outbox_materialization_is_idempotent_and_escapes_html() -> None:
    session_factory = factory()
    seed_event(session_factory)

    with session_factory() as session:
        assert notification_api.materialize_outbox(session) == 1
        assert notification_api.materialize_outbox(session) == 0
        item = session.scalar(select(NotificationMessage))
        assert item is not None
        assert "<script>" not in item.html_body
        assert "&lt;script&gt;" in item.html_body
        assert item.deduplication_key.startswith("outbox:")
        event = session.scalar(select(OutboxMessage))
        assert event is not None and event.published_at is not None


def test_successful_delivery_is_audited_once(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = factory()
    seed_event(session_factory)
    monkeypatch.setattr(notification_api, "_smtp_send", lambda item: f"<sent-{item.id}@test>")

    with session_factory() as session:
        notification_api.materialize_outbox(session)
        result = notification_api.dispatch_due(session)
        replay = notification_api.dispatch_due(session)
        item = session.scalar(select(NotificationMessage))
        attempts = session.scalar(select(func.count()).select_from(NotificationDeliveryAttempt))

    assert result == {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "deadLetter": 0,
        "uncertain": 0,
    }
    assert replay == {
        "claimed": 0,
        "sent": 0,
        "failed": 0,
        "deadLetter": 0,
        "uncertain": 0,
    }
    assert item is not None and item.status == "SENT"
    assert attempts == 1


def test_failed_delivery_is_redacted_and_moves_to_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = factory()
    seed_event(session_factory)

    def fail(_item):
        raise RuntimeError("relay rejected rm.test@synthetic.invalid")

    monkeypatch.setattr(notification_api, "_smtp_send", fail)
    with session_factory() as session:
        notification_api.materialize_outbox(session)
        item = session.scalar(select(NotificationMessage))
        assert item is not None
        item.max_attempts = 1
        session.commit()
        result = notification_api.dispatch_due(session)
        attempt = session.scalar(select(NotificationDeliveryAttempt))

    assert result["deadLetter"] == 1
    assert item.status == "DEAD_LETTER"
    assert item.last_error is not None and "[email-redacted]" in item.last_error
    assert attempt is not None and attempt.outcome == "FAILED"


def test_notification_list_is_admin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    session_factory = factory()
    app = application_for("notification-service")
    app.state.session_factory = session_factory
    app.dependency_overrides[current_principal] = lambda: Principal(
        subject="rm-01",
        username="rm.demo",
        roles={"RELATIONSHIP_MANAGER"},
    )

    response = TestClient(app).get("/internal/v1/notifications")

    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_daily_digest_is_deduplicated_and_contains_only_aggregate_kpis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFICATION_SCOPE_SIGNING_SECRET", "test-digest-scope-secret")
    session_factory = factory()
    with session_factory.begin() as session:
        session.add(
            NotificationDigestSubscription(
                id=deterministic_uuid("digest-subscription", "rm-01"),
                relationship_manager_id="rm-01",
                recipient_email="rm.demo@synthetic.invalid",
                timezone_name="Africa/Abidjan",
                delivery_hour=7,
                enabled=True,
                last_digest_date=None,
                last_notification_id=None,
                created_by="admin-test",
            )
        )

    async def fake_service_request(*_args, **_kwargs):
        return {
            "scope": {"relationshipManagerName": "CC Démonstration"},
            "kpis": {
                "portfolioCustomers": 42,
                "highPriorityCustomers": 5,
                "openOpportunities": 8,
                "actionsDue": 3,
            },
            "portfolio": [{"customerName": "Ne doit pas apparaître"}],
        }

    monkeypatch.setattr(notification_api, "service_request", fake_service_request)
    now = datetime(2030, 10, 30, 9, tzinfo=timezone.utc)
    with session_factory() as session:
        first = asyncio.run(
            notification_api.materialize_daily_digests(session, now=now, force=True)
        )
        second = asyncio.run(
            notification_api.materialize_daily_digests(session, now=now, force=True)
        )
        item = session.scalar(
            select(NotificationMessage).where(
                NotificationMessage.notification_type == "PORTFOLIO_DAILY_DIGEST"
            )
        )

    assert first == {"created": 1, "skipped": 0, "failed": 0}
    assert second == {"created": 0, "skipped": 1, "failed": 0}
    assert item is not None
    assert "42" in item.text_body and "Actions à échéance sous 7 jours : 3" in item.text_body
    assert "Ne doit pas apparaître" not in item.text_body
    assert "aucune décision de crédit" in item.text_body


def test_admin_can_upsert_digest_subscription_and_invalid_timezone_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    session_factory = factory()
    app = application_for("notification-service")
    app.state.session_factory = session_factory
    app.dependency_overrides[current_principal] = lambda: Principal(
        subject="admin-01",
        username="admin.demo",
        roles={"ADMIN"},
    )
    client = TestClient(app)

    invalid = client.put(
        "/internal/v1/notifications/digest-subscriptions/rm-01",
        json={
            "recipientEmail": "rm.demo@synthetic.invalid",
            "timezone": "Fuseau/Inconnu",
            "deliveryHour": 7,
            "enabled": True,
        },
    )
    created = client.put(
        "/internal/v1/notifications/digest-subscriptions/rm-01",
        json={
            "recipientEmail": "RM.Demo@synthetic.invalid",
            "timezone": "Africa/Abidjan",
            "deliveryHour": 7,
            "enabled": True,
        },
    )
    listed = client.get("/internal/v1/notifications/digest-subscriptions")

    assert invalid.status_code == 422
    assert created.status_code == 200
    assert created.json()["recipientEmail"] == "rm.demo@synthetic.invalid"
    assert listed.status_code == 200
    assert listed.json()["data"][0]["relationshipManagerId"] == "rm-01"
    app.dependency_overrides.clear()


def test_authenticated_smtp_without_tls_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = factory()
    seed_event(session_factory)
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USERNAME", "service-account")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.setenv("SMTP_SSL", "false")
    with session_factory() as session:
        notification_api.materialize_outbox(session)
        item = session.scalar(select(NotificationMessage))
        assert item is not None
        with pytest.raises(RuntimeError, match="requires TLS"):
            notification_api._smtp_send(item)


def test_stale_sending_is_quarantined_without_automatic_resend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = factory()
    seed_event(session_factory)
    with session_factory() as session:
        notification_api.materialize_outbox(session)
        item = session.scalar(select(NotificationMessage))
        assert item is not None
        item.status = "SENDING"
        item.attempt_count = 1
        item.locked_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        item.provider_message_id = f"<boa-{item.id}@test>"
        session.commit()

        monkeypatch.setattr(
            notification_api,
            "_smtp_send",
            lambda _item: pytest.fail("uncertain delivery must not be resent automatically"),
        )
        result = notification_api.dispatch_due(session)
        attempt = session.scalar(select(NotificationDeliveryAttempt))

    assert result["uncertain"] == 1
    assert result["claimed"] == 0
    assert item.status == "DELIVERY_UNCERTAIN"
    assert attempt is not None and attempt.outcome == "UNCERTAIN"
    assert attempt.provider_message_id == item.provider_message_id


def test_invalid_outbox_recipient_is_quarantined_after_bounded_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFICATION_OUTBOX_MAX_ATTEMPTS", "2")
    session_factory = factory()
    seed_event(session_factory, event_ref="invalid-recipient")
    with session_factory() as session:
        event = session.scalar(select(OutboxMessage))
        assert event is not None
        event.payload_json = {**event.payload_json, "recipientEmail": "invalid"}
        session.commit()
        assert notification_api.materialize_outbox(session) == 0
        assert event.published_at is None
        assert notification_api.materialize_outbox(session) == 0
        session.refresh(event)

    assert event.published_at is not None
    assert event.attempt_count == 2
    assert event.processing_status == "REJECTED"
    assert event.processing_error == "INVALID_OR_MISSING_VERIFIED_RECIPIENT"


def test_generic_service_cannot_generate_or_dispatch_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    session_factory = factory()
    app = application_for("notification-service")
    app.state.session_factory = session_factory
    app.dependency_overrides[current_principal] = lambda: Principal(
        subject="unrelated-service",
        username="unrelated-service",
        roles={"SERVICE"},
    )
    client = TestClient(app)

    generated = client.post("/internal/v1/notifications/digests/generate?force=true")
    dispatched = client.post("/internal/v1/notifications/dispatch")

    assert generated.status_code == 403
    assert dispatched.status_code == 403
    app.dependency_overrides.clear()


def test_blocked_action_event_is_not_materialized() -> None:
    session_factory = factory()
    seed_event(session_factory, event_ref="blocked-action")
    with session_factory() as session:
        event = session.scalar(select(OutboxMessage))
        assert event is not None
        event.processing_status = "BLOCKED"
        session.commit()
        created = notification_api.materialize_outbox(session)
        notifications = session.scalar(select(func.count()).select_from(NotificationMessage))

    assert created == 0
    assert notifications == 0
