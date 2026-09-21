from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    SIMULATED = "SIMULATED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    ROLLED_BACK = "ROLLED_BACK"


class PolicyAuditEventType(str, Enum):
    CREATED = "CREATED"
    VERSION_CREATED = "VERSION_CREATED"
    SIMULATED = "SIMULATED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ACTIVATED = "ACTIVATED"
    DISABLED = "DISABLED"
    ROLLED_BACK = "ROLLED_BACK"
    ROLLBACK_ACTIVATED = "ROLLBACK_ACTIVATED"


class DomainError(ValueError):
    """Erreur de règle d'invariant du domaine, indépendante de la persistance."""


class InvalidPolicyTransition(DomainError):
    pass


class PolicyApproval(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    approver_id: str = Field(alias="approverId", min_length=1)
    reason: str = Field(min_length=1)
    decided_at: datetime = Field(alias="decidedAt")


class ScoringPolicyAuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    event_id: UUID = Field(default_factory=uuid4, alias="eventId")
    policy_id: str = Field(alias="policyId", min_length=1)
    version: int = Field(ge=1)
    event_type: PolicyAuditEventType = Field(alias="eventType")
    actor_id: str = Field(alias="actorId", min_length=1)
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="occurredAt"
    )
    from_status: PolicyStatus | None = Field(default=None, alias="fromStatus")
    to_status: PolicyStatus | None = Field(default=None, alias="toStatus")
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoringPolicyVersion(BaseModel):
    """Version immuable d'une politique; aucune dépendance infrastructurelle."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    policy_id: str = Field(alias="policyId", min_length=1)
    version: int = Field(ge=1)
    weights: dict[str, Decimal]
    status: PolicyStatus = PolicyStatus.DRAFT
    effective_from: datetime | None = Field(default=None, alias="effectiveFrom")
    effective_to: datetime | None = Field(default=None, alias="effectiveTo")
    author_id: str = Field(alias="authorId", min_length=1)
    approver_id: str | None = Field(default=None, alias="approverId")
    approval_reason: str | None = Field(default=None, alias="approvalReason")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")
    reason: str | None = None
    simulation_id: str | None = Field(default=None, alias="simulationId")
    audit_events: tuple[ScoringPolicyAuditEvent, ...] = Field(
        default_factory=tuple, alias="auditEvents"
    )

    @field_validator("weights", mode="before")
    @classmethod
    def validate_weights(cls, value: Mapping[str, Any]) -> dict[str, Decimal]:
        if not isinstance(value, Mapping) or not value:
            raise ValueError("weights must contain at least one named component")
        converted: dict[str, Decimal] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("weight names must not be empty")
            if key in converted:
                raise ValueError(f"duplicate weight name: {key}")
            try:
                number = Decimal(str(raw_value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"weight {key!r} must be numeric") from exc
            if not number.is_finite() or number < 0:
                raise ValueError(f"weight {key!r} must be finite and non-negative")
            converted[key] = number
        # POC invariant: a policy is a normalized convex combination;
        # component names stay configurable.
        if sum(converted.values(), Decimal("0")) != Decimal("1"):
            raise ValueError("weights must sum exactly to 1")
        ml_weight = converted.get("ml", converted.get("propensity", Decimal("0")))
        if ml_weight > Decimal("0.5"):
            raise ValueError("ML weight must not exceed 0.5")
        return converted

    @model_validator(mode="after")
    def validate_consistency(self) -> ScoringPolicyVersion:
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effectiveTo must be later than effectiveFrom")
        if self.status == PolicyStatus.APPROVED:
            if not self.approver_id or not self.approval_reason or not self.approved_at:
                raise ValueError("APPROVED requires approver, approval reason and approval time")
            if self.approver_id == self.author_id:
                raise ValueError("author cannot approve the same policy version")
        if self.status in {
            PolicyStatus.PUBLISHED,
            PolicyStatus.ACTIVE,
        } and (not self.approver_id or not self.approval_reason or not self.approved_at):
            raise ValueError(f"{self.status.value} requires a recorded approval")
        if self.status == PolicyStatus.ACTIVE and self.effective_from is None:
            raise ValueError("ACTIVE requires effectiveFrom")
        if (
            self.status == PolicyStatus.ACTIVE
            and self.weights.get("ml", self.weights.get("propensity", Decimal("0"))) != 0
        ):
            raise ValueError("ACTIVE is restricted to RULES_ONLY while BOA labels are unavailable")
        return self

    @classmethod
    def create_draft(
        cls,
        *,
        policy_id: str,
        weights: Mapping[str, Any],
        author_id: str,
        version: int = 1,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> ScoringPolicyVersion:
        at = now or datetime.now(timezone.utc)
        draft = cls(
            policyId=policy_id,
            version=version,
            weights=dict(weights),
            status=PolicyStatus.DRAFT,
            authorId=author_id,
            reason=reason,
        )
        return draft._with_event(
            event_type=PolicyAuditEventType.CREATED
            if version == 1
            else PolicyAuditEventType.VERSION_CREATED,
            actor_id=author_id,
            occurred_at=at,
            to_status=PolicyStatus.DRAFT,
            reason=reason,
        )

    create = create_draft

    def _with_event(
        self,
        *,
        event_type: PolicyAuditEventType,
        actor_id: str,
        occurred_at: datetime,
        from_status: PolicyStatus | None = None,
        to_status: PolicyStatus | None = None,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **updates: Any,
    ) -> ScoringPolicyVersion:
        event = ScoringPolicyAuditEvent(
            policyId=self.policy_id,
            version=self.version,
            eventType=event_type,
            actorId=actor_id,
            occurredAt=occurred_at,
            fromStatus=from_status,
            toStatus=to_status,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        return self.model_copy(update={**updates, "audit_events": (*self.audit_events, event)})

    def transition(
        self,
        target: PolicyStatus,
        *,
        actor_id: str,
        reason: str | None = None,
        at: datetime | None = None,
        simulation_id: str | None = None,
    ) -> ScoringPolicyVersion:
        if not actor_id.strip():
            raise DomainError("actor_id is required")
        transitions: dict[PolicyStatus, frozenset[PolicyStatus]] = {
            PolicyStatus.DRAFT: frozenset({PolicyStatus.SIMULATED}),
            PolicyStatus.SIMULATED: frozenset({PolicyStatus.SUBMITTED}),
            PolicyStatus.SUBMITTED: frozenset({PolicyStatus.APPROVED}),
            PolicyStatus.APPROVED: frozenset({PolicyStatus.PUBLISHED}),
            PolicyStatus.PUBLISHED: frozenset({PolicyStatus.ACTIVE, PolicyStatus.DISABLED}),
            PolicyStatus.ACTIVE: frozenset({PolicyStatus.DISABLED, PolicyStatus.ROLLED_BACK}),
        }
        if target not in transitions.get(self.status, frozenset()):
            raise InvalidPolicyTransition(f"{self.status.value} -> {target.value} is not allowed")
        if target == PolicyStatus.SIMULATED and not (simulation_id or self.simulation_id):
            raise DomainError("SIMULATED requires simulation_id")
        if target == PolicyStatus.APPROVED:
            if actor_id == self.author_id:
                raise DomainError("author cannot approve the same policy version")
            if not reason or not reason.strip():
                raise DomainError("approval reason is required")
        if (
            target == PolicyStatus.ACTIVE
            and self.weights.get("ml", self.weights.get("propensity", Decimal("0"))) != 0
        ):
            raise DomainError("ACTIVE is restricted to RULES_ONLY while BOA labels are unavailable")
        if target in {PolicyStatus.DISABLED, PolicyStatus.ROLLED_BACK} and not reason:
            raise DomainError(f"{target.value} requires a reason")
        at = at or datetime.now(timezone.utc)
        event_type = {
            PolicyStatus.SIMULATED: PolicyAuditEventType.SIMULATED,
            PolicyStatus.SUBMITTED: PolicyAuditEventType.SUBMITTED,
            PolicyStatus.APPROVED: PolicyAuditEventType.APPROVED,
            PolicyStatus.PUBLISHED: PolicyAuditEventType.PUBLISHED,
            PolicyStatus.ACTIVE: PolicyAuditEventType.ACTIVATED,
            PolicyStatus.DISABLED: PolicyAuditEventType.DISABLED,
            PolicyStatus.ROLLED_BACK: PolicyAuditEventType.ROLLED_BACK,
        }[target]
        updates: dict[str, Any] = {"status": target}
        if simulation_id:
            updates["simulation_id"] = simulation_id
        if target == PolicyStatus.APPROVED:
            updates.update(approver_id=actor_id, approval_reason=reason, approved_at=at)
        if target == PolicyStatus.ACTIVE and self.effective_from is None:
            updates["effective_from"] = at
        return self._with_event(
            event_type=event_type,
            actor_id=actor_id,
            occurred_at=at,
            from_status=self.status,
            to_status=target,
            reason=reason,
            **updates,
        )

    def simulate(
        self, *, actor_id: str, simulation_id: str, at: datetime | None = None
    ) -> ScoringPolicyVersion:
        return self.transition(
            PolicyStatus.SIMULATED, actor_id=actor_id, simulation_id=simulation_id, at=at
        )

    def submit(
        self, *, actor_id: str, reason: str | None = None, at: datetime | None = None
    ) -> ScoringPolicyVersion:
        return self.transition(PolicyStatus.SUBMITTED, actor_id=actor_id, reason=reason, at=at)

    def approve(
        self, *, actor_id: str, reason: str, at: datetime | None = None
    ) -> ScoringPolicyVersion:
        return self.transition(PolicyStatus.APPROVED, actor_id=actor_id, reason=reason, at=at)

    def publish(self, *, actor_id: str, at: datetime | None = None) -> ScoringPolicyVersion:
        return self.transition(PolicyStatus.PUBLISHED, actor_id=actor_id, at=at)

    def activate(
        self, *, actor_id: str, effective_from: datetime | None = None, at: datetime | None = None
    ) -> ScoringPolicyVersion:
        activated = self.transition(PolicyStatus.ACTIVE, actor_id=actor_id, at=at)
        if effective_from is not None:
            if activated.effective_to and effective_from >= activated.effective_to:
                raise DomainError("effectiveFrom must precede effectiveTo")
            activated = activated.model_copy(update={"effective_from": effective_from})
        return activated

    def disable(
        self,
        *,
        actor_id: str,
        reason: str,
        effective_to: datetime | None = None,
        at: datetime | None = None,
    ) -> ScoringPolicyVersion:
        disabled = self.transition(PolicyStatus.DISABLED, actor_id=actor_id, reason=reason, at=at)
        return (
            disabled.model_copy(update={"effective_to": effective_to}) if effective_to else disabled
        )

    def rollback(
        self, *, actor_id: str, reason: str, at: datetime | None = None
    ) -> ScoringPolicyVersion:
        return self.transition(PolicyStatus.ROLLED_BACK, actor_id=actor_id, reason=reason, at=at)

    def new_version(
        self,
        *,
        weights: Mapping[str, Any],
        author_id: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> ScoringPolicyVersion:
        return ScoringPolicyVersion.create_draft(
            policy_id=self.policy_id,
            version=self.version + 1,
            weights=weights,
            author_id=author_id,
            reason=reason,
            now=at,
        )

    revise = new_version

    def is_effective(self, at: datetime) -> bool:
        return (
            self.status == PolicyStatus.ACTIVE
            and (self.effective_from is None or at >= self.effective_from)
            and (self.effective_to is None or at < self.effective_to)
        )


class ScoringPolicy(BaseModel):
    """Agrégat optionnel pour gérer l'historique et un rollback atomique en mémoire."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    policy_id: str = Field(alias="policyId", min_length=1)
    versions: tuple[ScoringPolicyVersion, ...] = Field(min_length=1)
    active_version: int | None = Field(default=None, alias="activeVersion")
    audit_events: tuple[ScoringPolicyAuditEvent, ...] = Field(
        default_factory=tuple, alias="auditEvents"
    )

    @model_validator(mode="after")
    def validate_history(self) -> ScoringPolicy:
        numbers = [version.version for version in self.versions]
        if len(numbers) != len(set(numbers)) or numbers != sorted(numbers):
            raise ValueError("versions must be unique and ordered")
        if any(version.policy_id != self.policy_id for version in self.versions):
            raise ValueError("all versions must belong to policy_id")
        if self.active_version is not None:
            active = [v for v in self.versions if v.version == self.active_version]
            if len(active) != 1 or active[0].status != PolicyStatus.ACTIVE:
                raise ValueError("activeVersion must point to exactly one ACTIVE version")
        return self

    @classmethod
    def create_draft(
        cls,
        *,
        policy_id: str,
        weights: Mapping[str, Any],
        author_id: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> ScoringPolicy:
        version = ScoringPolicyVersion.create_draft(
            policy_id=policy_id, weights=weights, author_id=author_id, reason=reason, now=at
        )
        return cls(policyId=policy_id, versions=(version,), auditEvents=version.audit_events)

    @property
    def current(self) -> ScoringPolicyVersion:
        return self.versions[-1]

    def add_version(
        self,
        *,
        weights: Mapping[str, Any],
        author_id: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> ScoringPolicy:
        version = self.current.new_version(
            weights=weights, author_id=author_id, reason=reason, at=at
        )
        return self.model_copy(
            update={
                "versions": (*self.versions, version),
                "audit_events": (*self.audit_events, *version.audit_events),
            }
        )

    def transition(
        self,
        target: PolicyStatus,
        *,
        actor_id: str,
        reason: str | None = None,
        simulation_id: str | None = None,
        at: datetime | None = None,
    ) -> ScoringPolicy:
        changed = self.current.transition(
            target, actor_id=actor_id, reason=reason, simulation_id=simulation_id, at=at
        )
        versions = (*self.versions[:-1], changed)
        active_version = (
            changed.version if changed.status == PolicyStatus.ACTIVE else self.active_version
        )
        return self.model_copy(
            update={
                "versions": versions,
                "active_version": active_version,
                "audit_events": (*self.audit_events, changed.audit_events[-1]),
            }
        )

    def rollback(
        self, *, target_version: int, actor_id: str, reason: str, at: datetime | None = None
    ) -> ScoringPolicy:
        if target_version == self.current.version:
            raise DomainError("rollback target must differ from current version")
        target = next((item for item in self.versions if item.version == target_version), None)
        if target is None:
            raise DomainError(f"unknown rollback target version: {target_version}")
        if target.status not in {
            PolicyStatus.PUBLISHED,
            PolicyStatus.ACTIVE,
            PolicyStatus.DISABLED,
        }:
            raise DomainError("rollback target must have been published or active")
        at = at or datetime.now(timezone.utc)
        source = self.current
        if source.status == PolicyStatus.ACTIVE:
            source = source.rollback(actor_id=actor_id, reason=reason, at=at)
        elif source.status not in {PolicyStatus.DISABLED, PolicyStatus.ROLLED_BACK}:
            raise InvalidPolicyTransition(
                "current version must be ACTIVE, DISABLED or ROLLED_BACK for rollback"
            )
        activation_event = ScoringPolicyAuditEvent(
            policyId=self.policy_id,
            version=target.version,
            eventType=PolicyAuditEventType.ROLLBACK_ACTIVATED,
            actorId=actor_id,
            occurredAt=at,
            fromStatus=target.status,
            toStatus=PolicyStatus.ACTIVE,
            reason=reason,
            metadata={"targetVersion": target_version},
        )
        restored = target.model_copy(
            update={
                "status": PolicyStatus.ACTIVE,
                "effective_from": at,
                "effective_to": None,
                "audit_events": (*target.audit_events, activation_event),
            }
        )
        versions = tuple(
            restored
            if item.version == target_version
            else source
            if item.version == self.current.version
            else item
            for item in self.versions
        )
        return self.model_copy(
            update={
                "versions": versions,
                "active_version": target_version,
                "audit_events": (*self.audit_events, *source.audit_events[-1:], activation_event),
            }
        )

    def version(self, number: int) -> ScoringPolicyVersion:
        try:
            return next(item for item in self.versions if item.version == number)
        except StopIteration as exc:
            raise DomainError(f"unknown policy version: {number}") from exc

    def is_effective(self, at: datetime) -> bool:
        return self.active_version is not None and self.version(self.active_version).is_effective(
            at
        )


__all__ = [
    "DomainError",
    "InvalidPolicyTransition",
    "PolicyApproval",
    "PolicyAuditEventType",
    "PolicyStatus",
    "ScoringPolicy",
    "ScoringPolicyAuditEvent",
    "ScoringPolicyVersion",
]

# Backward/terminology aliases for adapters that use the English aggregate naming.
OpportunityScoringPolicy = ScoringPolicy
OpportunityScoringPolicyVersion = ScoringPolicyVersion
AuditEvent = ScoringPolicyAuditEvent
Status = PolicyStatus

__all__ += ["AuditEvent", "OpportunityScoringPolicy", "OpportunityScoringPolicyVersion", "Status"]
