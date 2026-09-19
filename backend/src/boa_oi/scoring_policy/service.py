from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    ScoringPolicy as ScoringPolicyRow,
)
from boa_oi.models.entities import (
    ScoringPolicyAuditLog,
)
from boa_oi.models.entities import (
    ScoringPolicyVersion as ScoringPolicyVersionRow,
)
from boa_oi.platform import Problem, not_found
from boa_oi.scoring_policy.domain import (
    DomainError,
    PolicyStatus,
)
from boa_oi.scoring_policy.domain import (
    ScoringPolicy as PolicyAggregate,
)
from boa_oi.scoring_policy.domain import (
    ScoringPolicyVersion as PolicyVersion,
)

_MUTATING = {
    "CREATE",
    "VERSION_CREATED",
    "SIMULATE",
    "SUBMIT",
    "APPROVE",
    "PUBLISH",
    "ACTIVATE",
    "DISABLE",
    "ROLLBACK",
}


def _now(value: datetime | None = None) -> datetime:
    return value or datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _reason(reason: str | None) -> str:
    if not reason or not reason.strip():
        raise DomainError("reason is required")
    return reason.strip()


def _trace(trace_id: str | None) -> str:
    if not trace_id or not trace_id.strip():
        raise DomainError("correlation id is required")
    return trace_id.strip()


def _actor(actor_id: str | None) -> str:
    if not actor_id or not actor_id.strip():
        raise DomainError("actor id is required")
    return actor_id.strip()


def _weights(
    weights: Mapping[str, Any] | None, rules_weight: Any = None, ml_weight: Any = None
) -> dict[str, Decimal]:
    """Normalize the public weight shape to the two persisted model columns.

    The domain remains the source of truth for normalization.  ``propensity`` is
    accepted as a public synonym for the persisted ML component because older
    clients used that name; no default or environment-defined weight is used.
    """
    values: dict[str, Any] = dict(weights or {})
    if rules_weight is not None:
        values.setdefault("rules", rules_weight)
    if ml_weight is not None:
        values.setdefault("ml", ml_weight)
    rules = values.get("rules", values.get("rulesWeight", values.get("rules_weight")))
    ml = values.get("ml", values.get("propensity", values.get("mlWeight", values.get("ml_weight"))))
    if rules is None or ml is None:
        raise DomainError("weights must contain rules and ml components")
    try:
        return {"rules": Decimal(str(rules)), "ml": Decimal(str(ml))}
    except (ArithmeticError, ValueError) as exc:
        raise DomainError("rules and ml weights must be numeric") from exc


def checksum(weights: Mapping[str, Decimal]) -> str:
    payload = {key: str(value) for key, value in sorted(weights.items())}
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _weights_from_row(row: ScoringPolicyVersionRow) -> dict[str, Decimal]:
    return {"rules": Decimal(str(row.rules_weight)), "ml": Decimal(str(row.ml_weight))}


def _version_payload(version: PolicyVersion) -> dict[str, Any]:
    return version.model_dump(mode="json", by_alias=True)


def serialize_version(
    row: ScoringPolicyVersionRow | PolicyVersion,
    policy_id: str | None = None,
) -> dict[str, Any]:
    if isinstance(row, PolicyVersion):
        payload = _version_payload(row)
        payload["definitionChecksum"] = checksum(row.weights)
        payload["checksum"] = payload["definitionChecksum"]
        return payload
    weights = _weights_from_row(row)
    return {
        "policyId": policy_id or str(row.policy_id),
        "version": row.version,
        "weights": {key: float(value) for key, value in weights.items()},
        "rulesWeight": float(weights["rules"]),
        "mlWeight": float(weights["ml"]),
        "status": row.status,
        "effectiveFrom": row.effective_from.isoformat() if row.effective_from else None,
        "effectiveTo": row.effective_to.isoformat() if row.effective_to else None,
        "authorId": row.author_id,
        "approverId": row.approver_id,
        "approvalReason": row.approval_reason,
        "approvedAt": row.approved_at.isoformat() if row.approved_at else None,
        "reason": row.reason,
        "simulationId": row.simulation_id,
        "definitionChecksum": row.checksum,
        "checksum": row.checksum,
    }


def serialize_policy(session: Session, row: ScoringPolicyRow) -> dict[str, Any]:
    versions = list(
        session.scalars(
            select(ScoringPolicyVersionRow)
            .where(ScoringPolicyVersionRow.policy_id == row.id)
            .order_by(ScoringPolicyVersionRow.version)
        )
    )
    return {
        "id": str(row.id),
        "policyId": row.policy_id,
        "currentVersion": row.current_version,
        "activeVersion": row.active_version,
        "versions": [serialize_version(item, row.policy_id) for item in versions],
        "active": next(
            (
                serialize_version(item, row.policy_id)
                for item in versions
                if item.version == row.active_version
            ),
            None,
        ),
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


def _find_row(session: Session, policy_id: str) -> ScoringPolicyRow:
    row = session.scalar(select(ScoringPolicyRow).where(ScoringPolicyRow.policy_id == policy_id))
    if row is None:
        raise not_found("Scoring policy")
    return row


def find_policy(session: Session, policy_id: str) -> ScoringPolicyRow:
    return _find_row(session, policy_id)


def _find_version(
    session: Session, policy_id: str, version: int
) -> tuple[ScoringPolicyRow, ScoringPolicyVersionRow]:
    policy = _find_row(session, policy_id)
    row = session.scalar(
        select(ScoringPolicyVersionRow).where(
            ScoringPolicyVersionRow.policy_id == policy.id,
            ScoringPolicyVersionRow.version == version,
        )
    )
    if row is None:
        raise not_found("Scoring policy version")
    return policy, row


def find_version(session: Session, policy_id: str, version: int) -> ScoringPolicyVersionRow:
    return _find_version(session, policy_id, version)[1]


def _domain_version(row: ScoringPolicyVersionRow, policy_id: str) -> PolicyVersion:
    return PolicyVersion(
        policyId=policy_id,
        version=row.version,
        weights=_weights_from_row(row),
        status=PolicyStatus(row.status),
        effectiveFrom=row.effective_from,
        effectiveTo=row.effective_to,
        authorId=row.author_id,
        approverId=row.approver_id,
        approvalReason=row.approval_reason,
        approvedAt=row.approved_at,
        reason=row.reason,
        simulationId=row.simulation_id,
    )


def _aggregate(session: Session, policy: ScoringPolicyRow) -> PolicyAggregate:
    versions = list(
        session.scalars(
            select(ScoringPolicyVersionRow)
            .where(ScoringPolicyVersionRow.policy_id == policy.id)
            .order_by(ScoringPolicyVersionRow.version)
        )
    )
    return PolicyAggregate(
        policyId=policy.policy_id,
        versions=tuple(_domain_version(item, policy.policy_id) for item in versions),
        activeVersion=policy.active_version,
    )


def _snapshot(
    row: ScoringPolicyVersionRow | dict[str, Any] | None,
    policy_id: str | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return row if isinstance(row, dict) else serialize_version(row, policy_id)


def _audit(
    session: Session,
    policy: ScoringPolicyRow,
    version: int,
    action: str,
    actor_id: str,
    trace_id: str,
    reason: str,
    old: ScoringPolicyVersionRow | dict[str, Any] | None,
    new: ScoringPolicyVersionRow | dict[str, Any] | None,
    at: datetime,
) -> None:
    session.add(
        ScoringPolicyAuditLog(
            policy_id=policy.id,
            policy_version=version,
            action=action,
            user_id=actor_id,
            timestamp=at,
            old_value_json=_snapshot(old, policy.policy_id),
            new_value_json=_snapshot(new, policy.policy_id),
            reason=reason,
            trace_id=trace_id,
        )
    )


def _apply_version(row: ScoringPolicyVersionRow, version: PolicyVersion) -> None:
    row.rules_weight = version.weights["rules"]
    row.ml_weight = version.weights["ml"]
    row.status = version.status.value
    row.effective_from = version.effective_from
    row.effective_to = version.effective_to
    row.author_id = version.author_id
    row.approver_id = version.approver_id
    row.approved_at = version.approved_at
    row.approval_reason = version.approval_reason
    row.reason = version.reason
    row.simulation_id = version.simulation_id
    row.checksum = checksum(version.weights)


def _domain_problem(exc: Exception) -> Problem:
    message = str(exc)
    if "author cannot approve" in message:
        return Problem(403, "SELF_APPROVAL_FORBIDDEN", message)
    if isinstance(exc, ValueError) and "reason" in message.lower():
        return Problem(422, "REASON_REQUIRED", message)
    if "is not allowed" in message:
        return Problem(409, "INVALID_POLICY_TRANSITION", message)
    return Problem(422, "INVALID_POLICY", message)


def create_policy(
    session: Session,
    policy_id: str,
    weights: Mapping[str, Any],
    actor_id: str,
    reason: str,
    trace_id: str,
    at: datetime | None = None,
) -> ScoringPolicyRow:
    at = _now(at)
    actor_id, trace_id, reason = _actor(actor_id), _trace(trace_id), _reason(reason)
    normalized = _weights(weights)
    if session.scalar(select(ScoringPolicyRow).where(ScoringPolicyRow.policy_id == policy_id)):
        raise Problem(409, "POLICY_EXISTS", "The scoring policy already exists.")
    try:
        draft = PolicyAggregate.create_draft(
            policy_id=policy_id, weights=normalized, author_id=actor_id, reason=reason, at=at
        ).current
    except (DomainError, ValueError) as exc:
        raise _domain_problem(exc) from exc
    policy = ScoringPolicyRow(
        policy_id=policy_id, current_version=1, active_version=None, created_by=actor_id
    )
    session.add(policy)
    session.flush()
    row = ScoringPolicyVersionRow(
        policy_id=policy.id,
        version=1,
        rules_weight=normalized["rules"],
        ml_weight=normalized["ml"],
        status=draft.status.value,
        author_id=actor_id,
        reason=reason,
        checksum=checksum(normalized),
        created_at=at,
    )
    session.add(row)
    session.flush()
    _audit(session, policy, 1, "CREATED", actor_id, trace_id, reason, None, row, at)
    return policy


def create_version(
    session: Session,
    policy_id: str,
    weights: Mapping[str, Any],
    actor_id: str,
    reason: str,
    trace_id: str,
    at: datetime | None = None,
) -> ScoringPolicyVersionRow:
    policy = _find_row(session, policy_id)
    at = _now(at)
    actor_id, trace_id, reason = _actor(actor_id), _trace(trace_id), _reason(reason)
    normalized = _weights(weights)
    current = session.scalar(
        select(ScoringPolicyVersionRow).where(
            ScoringPolicyVersionRow.policy_id == policy.id,
            ScoringPolicyVersionRow.version == policy.current_version,
        )
    )
    if current is None:
        raise not_found("Current scoring policy version")
    try:
        draft = (
            _aggregate(session, policy)
            .add_version(weights=normalized, author_id=actor_id, reason=reason, at=at)
            .current
        )
    except (DomainError, ValueError) as exc:
        raise _domain_problem(exc) from exc
    row = ScoringPolicyVersionRow(
        policy_id=policy.id,
        version=draft.version,
        rules_weight=normalized["rules"],
        ml_weight=normalized["ml"],
        status="DRAFT",
        author_id=actor_id,
        reason=reason,
        checksum=checksum(normalized),
        created_at=at,
    )
    policy.current_version = draft.version
    session.add(row)
    session.flush()
    _audit(
        session,
        policy,
        row.version,
        "VERSION_CREATED",
        actor_id,
        trace_id,
        reason,
        current,
        row,
        at,
    )
    return row


def transition_policy(
    session: Session,
    policy_id: str,
    version: int,
    target: PolicyStatus,
    actor_id: str,
    reason: str,
    trace_id: str,
    *,
    simulation_id: str | None = None,
    effective_from: datetime | None = None,
    at: datetime | None = None,
) -> ScoringPolicyVersionRow:
    policy, row = _find_version(session, policy_id, version)
    at = _now(at)
    actor_id, trace_id, reason = _actor(actor_id), _trace(trace_id), _reason(reason)
    old_payload = serialize_version(row, policy.policy_id)
    old_state = {
        "status": row.status,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "approver_id": row.approver_id,
        "approval_reason": row.approval_reason,
        "approved_at": row.approved_at,
        "simulation_id": row.simulation_id,
    }
    aggregate = _aggregate(session, policy)
    try:
        if target == PolicyStatus.SIMULATED:
            simulation_id = simulation_id or str(uuid4())
            changed = aggregate.transition(
                target, actor_id=actor_id, reason=reason, simulation_id=simulation_id, at=at
            ).current
        elif target == PolicyStatus.ACTIVE:
            changed = aggregate.transition(target, actor_id=actor_id, reason=reason, at=at).current
            if effective_from is not None:
                changed = changed.model_copy(update={"effective_from": effective_from})
        else:
            changed = aggregate.transition(target, actor_id=actor_id, reason=reason, at=at).current
    except (DomainError, ValueError) as exc:
        raise _domain_problem(exc) from exc
    if target == PolicyStatus.ACTIVE:
        with session.no_autoflush:
            previous = list(
                session.scalars(
                    select(ScoringPolicyVersionRow).where(
                        ScoringPolicyVersionRow.policy_id == policy.id,
                        ScoringPolicyVersionRow.status == "ACTIVE",
                        ScoringPolicyVersionRow.version != version,
                    )
                )
            )
        for previous_row in previous:
            previous_old = serialize_version(previous_row, policy.policy_id)
            previous_row.status = "DISABLED"
            previous_row.effective_to = changed.effective_from or at
            _audit(
                session,
                policy,
                previous_row.version,
                "DISABLED",
                actor_id,
                trace_id,
                reason,
                previous_old,
                previous_row,
                at,
            )
        if previous:
            session.flush()
    _apply_version(row, changed)
    if target == PolicyStatus.ACTIVE:
        policy.active_version = version
    elif target == PolicyStatus.DISABLED and policy.active_version == version:
        policy.active_version = None
        if row.effective_to is None:
            row.effective_to = at
    session.flush()
    old_json = dict(old_payload)
    old_json.update(
        {
            "status": old_state["status"],
            "effectiveFrom": _iso(old_state["effective_from"]),
            "effectiveTo": _iso(old_state["effective_to"]),
            "approverId": old_state["approver_id"],
            "approvalReason": old_state["approval_reason"],
            "approvedAt": _iso(old_state["approved_at"]),
            "simulationId": old_state["simulation_id"],
        }
    )
    _audit(session, policy, version, target.value, actor_id, trace_id, reason, old_json, row, at)
    return row


def rollback_policy(
    session: Session,
    policy_id: str,
    target_version: int,
    actor_id: str,
    reason: str,
    trace_id: str,
    at: datetime | None = None,
) -> ScoringPolicyVersionRow:
    policy = _find_row(session, policy_id)
    target = find_version(session, policy_id, target_version)
    current = find_version(session, policy_id, policy.current_version)
    at = _now(at)
    actor_id, trace_id, reason = _actor(actor_id), _trace(trace_id), _reason(reason)
    before_target = serialize_version(target, policy.policy_id)
    before_current = serialize_version(current, policy.policy_id)
    try:
        aggregate = _aggregate(session, policy).rollback(
            target_version=target_version, actor_id=actor_id, reason=reason, at=at
        )
    except (DomainError, ValueError) as exc:
        raise _domain_problem(exc) from exc
    version_models = {item.version: item for item in aggregate.versions}
    current_model = version_models.get(policy.current_version)
    if current_model is not None and current.version != target_version:
        _apply_version(current, current_model)
        session.flush()
    target_model = version_models.get(target_version)
    if target_model is None:
        raise Problem(409, "ROLLBACK_TARGET_MISSING", "Rollback target is no longer available.")
    _apply_version(target, target_model)
    policy.active_version = target_version
    session.flush()
    _audit(
        session,
        policy,
        policy.current_version,
        "ROLLBACK",
        actor_id,
        trace_id,
        reason,
        before_current,
        current,
        at,
    )
    _audit(
        session,
        policy,
        target_version,
        "ROLLBACK_ACTIVATED",
        actor_id,
        trace_id,
        reason,
        before_target,
        target,
        at,
    )
    return target


def audit_events(session: Session, policy_id: str) -> list[dict[str, Any]]:
    policy = _find_row(session, policy_id)
    rows = list(
        session.scalars(
            select(ScoringPolicyAuditLog)
            .where(ScoringPolicyAuditLog.policy_id == policy.id)
            .order_by(ScoringPolicyAuditLog.timestamp, ScoringPolicyAuditLog.id)
        )
    )
    return [
        {
            "id": str(item.id),
            "policyId": policy_id,
            "version": item.policy_version,
            "action": item.action,
            "userId": item.user_id,
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            "oldValue": item.old_value_json,
            "newValue": item.new_value_json,
            "reason": item.reason,
            "traceId": item.trace_id,
        }
        for item in rows
    ]


def active_policy(session: Session, at: datetime | None = None) -> ScoringPolicyVersionRow | None:
    """Return the effective ACTIVE version, never a policy-defined fallback."""
    at = _now(at)
    return session.scalar(
        select(ScoringPolicyVersionRow)
        .where(
            ScoringPolicyVersionRow.status == "ACTIVE",
            (ScoringPolicyVersionRow.effective_from.is_(None))
            | (ScoringPolicyVersionRow.effective_from <= at),
            (ScoringPolicyVersionRow.effective_to.is_(None))
            | (ScoringPolicyVersionRow.effective_to > at),
        )
        .order_by(
            ScoringPolicyVersionRow.effective_from.desc(), ScoringPolicyVersionRow.created_at.desc()
        )
    )


# Repository spelling used by integrations and tests.
class ScoringPolicyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, policy_id: str) -> ScoringPolicyRow:
        return find_policy(self.session, policy_id)

    def get_version(self, policy_id: str, version: int) -> ScoringPolicyVersionRow:
        return find_version(self.session, policy_id, version)

    def active(self, at: datetime | None = None) -> ScoringPolicyVersionRow | None:
        return active_policy(self.session, at)


__all__ = [
    "ScoringPolicyRepository",
    "active_policy",
    "audit_events",
    "checksum",
    "create_policy",
    "create_version",
    "find_policy",
    "find_version",
    "rollback_policy",
    "serialize_policy",
    "serialize_version",
    "transition_policy",
]

# Avoid a hard dependency on a particular API naming convention.
get_policy = find_policy
get_version = find_version
