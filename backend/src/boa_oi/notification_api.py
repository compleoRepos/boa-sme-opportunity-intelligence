from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import re
import smtplib
import ssl
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from boa_oi.http_clients import service_request
from boa_oi.models.entities import (
    NotificationDeliveryAttempt,
    NotificationDigestSubscription,
    NotificationMessage,
    OutboxMessage,
)
from boa_oi.platform import (
    Principal,
    Problem,
    auth_disabled,
    create_service_app,
    current_principal,
    decode_cursor,
    get_session,
    not_found,
    page_response,
    reject_unknown_filters,
    require_roles,
)
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "notification-service",
    "Transactional SMTP notifications with outbox deduplication and delivery audit.",
)
logger = logging.getLogger("boa.notification")
PREFIX = "/internal/v1"
SUPPORTED_EVENT = "ACTION_NOTIFICATION_REQUESTED"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
EMAIL_REDACTION = re.compile(r"[\w.+-]+@[\w.-]+")


def portfolio_url() -> str:
    return os.getenv("PORTFOLIO_SERVICE_URL", "http://portfolio:8080").rstrip("/")


class DigestSubscriptionInput(BaseModel):
    recipientEmail: str = Field(min_length=3, max_length=254)
    timezone: str = Field(default="Africa/Abidjan", min_length=1, max_length=80)
    deliveryHour: int = Field(default=7, ge=0, le=23)
    enabled: bool = True


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _serialize(item: NotificationMessage) -> dict[str, Any]:
    return {
        "notificationId": str(item.id),
        "type": item.notification_type,
        "recipient": item.recipient_email,
        "subject": item.subject,
        "status": item.status,
        "attemptCount": item.attempt_count,
        "maxAttempts": item.max_attempts,
        "nextAttemptAt": item.next_attempt_at.isoformat(),
        "sentAt": item.sent_at.isoformat() if item.sent_at else None,
        "providerMessageId": item.provider_message_id,
        "lastError": item.last_error,
        "correlationId": item.correlation_id,
        "createdAt": item.created_at.isoformat(),
    }


def _render_action_notification(payload: dict[str, Any]) -> tuple[str, str, str]:
    action_type = str(payload.get("actionType") or "ACTION_COMMERCIALE")
    due_at = str(payload.get("dueAt") or "à planifier")
    opportunity_id = str(payload.get("opportunityId") or "non renseignée")
    subject = "BOA SME — rappel d'action commerciale"
    text_body = (
        "Une action commerciale vous est assignée.\n"
        f"Type : {action_type}\n"
        f"Échéance : {due_at}\n"
        f"Opportunité : {opportunity_id}\n\n"
        "Connectez-vous à BOA SME Opportunity Intelligence pour consulter le dossier. "
        "Ce message ne contient aucune décision de crédit."
    )
    html_body = (
        "<p>Une action commerciale vous est assignée.</p>"
        f"<p><strong>Type :</strong> {html.escape(action_type)}<br>"
        f"<strong>Échéance :</strong> {html.escape(due_at)}<br>"
        f"<strong>Opportunité :</strong> {html.escape(opportunity_id)}</p>"
        "<p>Connectez-vous à BOA SME Opportunity Intelligence pour consulter le dossier. "
        "Ce message ne contient aucune décision de crédit.</p>"
    )
    return subject, text_body, html_body


def _serialize_subscription(item: NotificationDigestSubscription) -> dict[str, Any]:
    return {
        "relationshipManagerId": item.relationship_manager_id,
        "recipientEmail": item.recipient_email,
        "timezone": item.timezone_name,
        "deliveryHour": item.delivery_hour,
        "enabled": item.enabled,
        "lastDigestDate": item.last_digest_date.isoformat() if item.last_digest_date else None,
        "updatedAt": item.updated_at.isoformat(),
    }


def _render_daily_digest(dashboard: dict[str, Any], digest_date: date) -> tuple[str, str, str]:
    kpis = dashboard.get("kpis", {})
    scope = dashboard.get("scope", {})
    manager_name = str(scope.get("relationshipManagerName") or "Chargé de clientèle")
    values = {
        "portfolio": int(kpis.get("portfolioCustomers") or 0),
        "high": int(kpis.get("highPriorityCustomers") or 0),
        "opportunities": int(kpis.get("openOpportunities") or 0),
        "actions": int(kpis.get("actionsDue") or 0),
    }
    subject = f"BOA SME — synthèse quotidienne du {digest_date.isoformat()}"
    text_body = (
        f"Bonjour {manager_name},\n\n"
        f"Clients du portefeuille : {values['portfolio']}\n"
        f"Clients prioritaires P1 : {values['high']}\n"
        f"Opportunités ouvertes : {values['opportunities']}\n"
        f"Actions à échéance sous 7 jours : {values['actions']}\n\n"
        "Connectez-vous à BOA SME Opportunity Intelligence pour consulter les dossiers. "
        "Ces priorités sont une aide commerciale et ne constituent aucune décision de crédit."
    )
    html_body = (
        f"<p>Bonjour {html.escape(manager_name)},</p>"
        "<p>Voici votre synthèse commerciale quotidienne :</p>"
        "<ul>"
        f"<li>Clients du portefeuille : <strong>{values['portfolio']}</strong></li>"
        f"<li>Clients prioritaires P1 : <strong>{values['high']}</strong></li>"
        f"<li>Opportunités ouvertes : <strong>{values['opportunities']}</strong></li>"
        f"<li>Actions à échéance sous 7 jours : <strong>{values['actions']}</strong></li>"
        "</ul>"
        "<p>Connectez-vous à BOA SME Opportunity Intelligence pour consulter les dossiers. "
        "Ces priorités sont une aide commerciale et ne constituent aucune décision de crédit.</p>"
    )
    return subject, text_body, html_body


async def materialize_daily_digests(
    session: Session,
    *,
    now: datetime | None = None,
    force: bool = False,
    incoming_authorization: str | None = None,
    dev_principal: str | None = None,
) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    subscriptions = list(
        session.scalars(
            select(NotificationDigestSubscription)
            .where(NotificationDigestSubscription.enabled.is_(True))
            .order_by(NotificationDigestSubscription.relationship_manager_id)
        )
    )
    created = 0
    skipped = 0
    failed = 0
    for subscription in subscriptions:
        local_now = current.astimezone(ZoneInfo(subscription.timezone_name))
        digest_date = local_now.date()
        if not force and (
            local_now.hour < subscription.delivery_hour
            or subscription.last_digest_date == digest_date
        ):
            skipped += 1
            continue
        deduplication_key = (
            f"daily-digest:{subscription.relationship_manager_id}:{digest_date.isoformat()}"
        )
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            claimed = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": deduplication_key},
            )
            if not claimed:
                skipped += 1
                continue
        existing = session.scalar(
            select(NotificationMessage).where(
                NotificationMessage.deduplication_key == deduplication_key
            )
        )
        if existing is not None:
            subscription.last_digest_date = digest_date
            subscription.last_notification_id = existing.id
            session.commit()
            skipped += 1
            continue
        try:
            scope_secret = os.getenv("NOTIFICATION_SCOPE_SIGNING_SECRET")
            if not scope_secret:
                raise Problem(
                    503,
                    "NOTIFICATION_SCOPE_NOT_CONFIGURED",
                    "Digest scope is unavailable.",
                )
            signature = hmac.new(
                scope_secret.encode(),
                subscription.relationship_manager_id.encode(),
                hashlib.sha256,
            ).hexdigest()
            dashboard = await service_request(
                "GET",
                f"{portfolio_url()}/internal/v1/notification-digests/"
                f"{subscription.relationship_manager_id}",
                correlation_id=f"daily-digest-{digest_date.isoformat()}",
                incoming_authorization=incoming_authorization,
                dev_principal=dev_principal,
                headers={"X-BOA-Digest-Signature": signature},
            )
        except Problem:
            session.rollback()
            failed += 1
            continue
        subject, text_body, html_body = _render_daily_digest(dashboard, digest_date)
        notification_id = deterministic_uuid("daily-digest", deduplication_key)
        session.add(
            NotificationMessage(
                id=notification_id,
                deduplication_key=deduplication_key,
                event_id=None,
                notification_type="PORTFOLIO_DAILY_DIGEST",
                recipient_email=subscription.recipient_email,
                recipient_name=dashboard.get("scope", {}).get("relationshipManagerName"),
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                status="PENDING",
                attempt_count=0,
                max_attempts=5,
                next_attempt_at=current,
                correlation_id=f"daily-digest-{digest_date.isoformat()}",
                created_by="notification-worker",
            )
        )
        subscription.last_digest_date = digest_date
        subscription.last_notification_id = notification_id
        subscription.updated_at = current
        session.commit()
        created += 1
    return {"created": created, "skipped": skipped, "failed": failed}


def materialize_outbox(session: Session, *, limit: int = 100) -> int:
    stmt = (
        select(OutboxMessage)
        .where(
            OutboxMessage.event_type == SUPPORTED_EVENT,
            OutboxMessage.published_at.is_(None),
            or_(
                OutboxMessage.processing_status.is_(None),
                OutboxMessage.processing_status != "BLOCKED",
            ),
        )
        .order_by(OutboxMessage.occurred_at)
        .limit(limit)
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    events = list(session.scalars(stmt))
    created = 0
    now = datetime.now(timezone.utc)
    max_invalid_attempts = int(os.getenv("NOTIFICATION_OUTBOX_MAX_ATTEMPTS", "3"))
    for event in events:
        deduplication_key = f"outbox:{event.id}"
        existing = session.scalar(
            select(NotificationMessage).where(
                NotificationMessage.deduplication_key == deduplication_key
            )
        )
        if existing is None:
            recipient = str(event.payload_json.get("recipientEmail") or "").strip().lower()
            if not EMAIL_PATTERN.fullmatch(recipient):
                event.attempt_count += 1
                if event.attempt_count >= max_invalid_attempts:
                    event.processing_status = "REJECTED"
                    event.processing_error = "INVALID_OR_MISSING_VERIFIED_RECIPIENT"
                    event.published_at = now
                logger.warning("notification event %s has no valid recipient", event.id)
                continue
            subject, text_body, html_body = _render_action_notification(event.payload_json)
            session.add(
                NotificationMessage(
                    id=deterministic_uuid("notification", str(event.id)),
                    deduplication_key=deduplication_key,
                    event_id=event.id,
                    notification_type="ACTION_DUE_REMINDER",
                    recipient_email=recipient,
                    recipient_name=event.payload_json.get("recipientName"),
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    status="PENDING",
                    attempt_count=0,
                    max_attempts=5,
                    next_attempt_at=now,
                    correlation_id=event.correlation_id,
                    created_by="notification-worker",
                )
            )
            created += 1
        event.published_at = now
        event.processing_status = "PROCESSED"
        event.processing_error = None
    session.commit()
    return created


def _smtp_send(item: NotificationMessage) -> str:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        raise RuntimeError("SMTP transport is not configured")
    port = int(os.getenv("SMTP_PORT", "25"))
    sender = os.getenv("SMTP_FROM", "boa-sme-opportunity@localhost")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_starttls = os.getenv("SMTP_STARTTLS", "false").lower() == "true"
    use_ssl = os.getenv("SMTP_SSL", "false").lower() == "true"
    if use_starttls and use_ssl:
        raise RuntimeError("SMTP_STARTTLS and SMTP_SSL are mutually exclusive")
    if username and not (use_starttls or use_ssl):
        raise RuntimeError("Authenticated SMTP requires TLS")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = item.recipient_email
    message["Subject"] = item.subject
    message["Date"] = formatdate(localtime=False)
    domain = os.getenv("SMTP_MESSAGE_ID_DOMAIN", "boa.local")
    message_id = item.provider_message_id or f"<boa-{item.id}@{domain}>"
    message["Message-ID"] = message_id
    message["X-BOA-Notification-ID"] = str(item.id)
    message["X-BOA-Correlation-ID"] = item.correlation_id
    message.set_content(item.text_body)
    message.add_alternative(item.html_body, subtype="html")
    timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    tls_context = ssl.create_default_context()
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    smtp_kwargs: dict[str, Any] = {"host": host, "port": port, "timeout": timeout}
    if use_ssl:
        smtp_kwargs["context"] = tls_context
    with smtp_class(**smtp_kwargs) as smtp:
        smtp.ehlo()
        if use_starttls:
            smtp.starttls(context=tls_context)
            smtp.ehlo()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(message)
    return message_id


def _redacted_error(exc: Exception) -> str:
    value = EMAIL_REDACTION.sub("[email-redacted]", str(exc))
    return f"{type(exc).__name__}: {value}"[:500]


def _quarantine_uncertain_deliveries(session: Session, *, stale_before: datetime) -> int:
    stmt = select(NotificationMessage).where(
        NotificationMessage.status == "SENDING",
        NotificationMessage.locked_at < stale_before,
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    items = list(session.scalars(stmt))
    for item in items:
        item.status = "DELIVERY_UNCERTAIN"
        item.locked_at = None
        item.last_error = (
            "SMTP result is uncertain after worker interruption; reconcile the stable Message-ID "
            "before an explicit retry."
        )
        attempt_id = deterministic_uuid(
            "notification-attempt", str(item.id), str(item.attempt_count)
        )
        if session.get(NotificationDeliveryAttempt, attempt_id) is None:
            session.add(
                NotificationDeliveryAttempt(
                    id=attempt_id,
                    notification_id=item.id,
                    attempt_number=item.attempt_count,
                    outcome="UNCERTAIN",
                    provider_message_id=item.provider_message_id,
                    error_redacted=item.last_error,
                )
            )
    if items:
        session.commit()
    return len(items)


def dispatch_due(session: Session, *, limit: int = 50) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=5)
    uncertain = _quarantine_uncertain_deliveries(session, stale_before=stale_before)
    stmt = (
        select(NotificationMessage)
        .where(
            NotificationMessage.status.in_(["PENDING", "RETRY"]),
            NotificationMessage.next_attempt_at <= now,
        )
        .order_by(NotificationMessage.next_attempt_at, NotificationMessage.created_at)
        .limit(limit)
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    items = list(session.scalars(stmt))
    sent = 0
    failed = 0
    dead_letter = 0
    for item in items:
        item.status = "SENDING"
        item.locked_at = now
        item.attempt_count += 1
        item.provider_message_id = (
            f"<boa-{item.id}@{os.getenv('SMTP_MESSAGE_ID_DOMAIN', 'boa.local')}>"
        )
        item.updated_at = now
        session.commit()
        try:
            message_id = _smtp_send(item)
        except (OSError, RuntimeError, ValueError, smtplib.SMTPException) as exc:
            error = _redacted_error(exc)
            item.last_error = error
            item.locked_at = None
            if item.attempt_count >= item.max_attempts:
                item.status = "DEAD_LETTER"
                dead_letter += 1
            else:
                item.status = "RETRY"
                item.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=min(3600, 30 * (2 ** (item.attempt_count - 1)))
                )
            session.add(
                NotificationDeliveryAttempt(
                    id=deterministic_uuid(
                        "notification-attempt", str(item.id), str(item.attempt_count)
                    ),
                    notification_id=item.id,
                    attempt_number=item.attempt_count,
                    outcome="FAILED",
                    error_redacted=error,
                )
            )
            failed += 1
        else:
            item.status = "SENT"
            item.sent_at = datetime.now(timezone.utc)
            item.locked_at = None
            item.provider_message_id = message_id
            item.last_error = None
            session.add(
                NotificationDeliveryAttempt(
                    id=deterministic_uuid(
                        "notification-attempt", str(item.id), str(item.attempt_count)
                    ),
                    notification_id=item.id,
                    attempt_number=item.attempt_count,
                    outcome="SENT",
                    provider_message_id=message_id,
                )
            )
            sent += 1
        session.commit()
    return {
        "claimed": len(items),
        "sent": sent,
        "failed": failed,
        "deadLetter": dead_letter,
        "uncertain": uncertain,
    }


@app.get(
    f"{PREFIX}/notifications/digest-subscriptions",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Notifications"],
)
def list_digest_subscriptions(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    items = list(
        session.scalars(
            select(NotificationDigestSubscription).order_by(
                NotificationDigestSubscription.relationship_manager_id
            )
        )
    )
    return {"data": [_serialize_subscription(item) for item in items]}


@app.put(
    f"{PREFIX}/notifications/digest-subscriptions/{{relationship_manager_id}}",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Notifications"],
)
def upsert_digest_subscription(
    relationship_manager_id: str,
    payload: DigestSubscriptionInput,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    recipient = payload.recipientEmail.strip().lower()
    if not EMAIL_PATTERN.fullmatch(recipient):
        raise Problem(422, "VALIDATION_ERROR", "The recipient email is invalid.")
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        raise Problem(422, "VALIDATION_ERROR", "The timezone is unknown.") from exc
    item = session.scalar(
        select(NotificationDigestSubscription).where(
            NotificationDigestSubscription.relationship_manager_id == relationship_manager_id
        )
    )
    if item is None:
        item = NotificationDigestSubscription(
            id=deterministic_uuid("digest-subscription", relationship_manager_id),
            relationship_manager_id=relationship_manager_id,
            recipient_email=recipient,
            timezone_name=payload.timezone,
            delivery_hour=payload.deliveryHour,
            enabled=payload.enabled,
            last_digest_date=None,
            last_notification_id=None,
            created_by=principal.subject,
        )
        session.add(item)
    else:
        item.recipient_email = recipient
        item.timezone_name = payload.timezone
        item.delivery_hour = payload.deliveryHour
        item.enabled = payload.enabled
        item.updated_at = datetime.now(timezone.utc)
    session.flush()
    return _serialize_subscription(item)


@app.post(
    f"{PREFIX}/notifications/digests/generate",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Notifications"],
)
async def generate_digests(
    force: bool = False,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    dev_scope = None
    if auth_disabled():
        dev_scope = json.dumps(
            {
                "subject": "notification-service",
                "roles": ["NOTIFICATION_DIGEST_READER"],
            }
        )
    generated = await materialize_daily_digests(
        session,
        force=force,
        incoming_authorization=None,
        dev_principal=dev_scope,
    )
    return {**generated, **dispatch_due(session)}


@app.get(
    f"{PREFIX}/notifications",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Notifications"],
)
def list_notifications(
    request: Request,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
    cursor: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"status", "pageSize", "cursor"})
    offset = decode_cursor(cursor)
    stmt = select(NotificationMessage)
    if status_filter:
        if status_filter not in {
            "PENDING",
            "SENDING",
            "RETRY",
            "SENT",
            "DELIVERY_UNCERTAIN",
            "DEAD_LETTER",
        }:
            raise Problem(422, "VALIDATION_ERROR", "Unknown notification status.")
        stmt = stmt.where(NotificationMessage.status == status_filter)
    items = list(
        session.scalars(
            stmt.order_by(NotificationMessage.created_at.desc()).offset(offset).limit(page_size + 1)
        )
    )
    return page_response(
        request,
        [_serialize(item) for item in items],
        page_size=page_size,
        offset=offset,
        total_count=None,
    )


@app.post(
    f"{PREFIX}/notifications/dispatch",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Notifications"],
)
def dispatch_notifications(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    materialized = materialize_outbox(session, limit=limit)
    result = dispatch_due(session, limit=limit)
    return {"materialized": materialized, **result}


@app.post(
    f"{PREFIX}/notifications/{{notification_id}}/retry",
    dependencies=[Depends(require_roles("ADMIN"))],
    tags=["Notifications"],
)
def retry_notification(
    notification_id: UUID,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(NotificationMessage, notification_id)
    if item is None:
        raise not_found("Notification")
    if item.status not in {"DEAD_LETTER", "DELIVERY_UNCERTAIN"}:
        raise Problem(
            409,
            "NOTIFICATION_NOT_RETRYABLE",
            "Only dead-letter or reconciled uncertain messages can be retried.",
        )
    item.status = "RETRY"
    item.next_attempt_at = datetime.now(timezone.utc)
    item.locked_at = None
    item.last_error = None
    session.flush()
    return _serialize(item)
