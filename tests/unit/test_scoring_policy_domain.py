from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from boa_oi.scoring_policy import (
    DomainError,
    InvalidPolicyTransition,
    PolicyAuditEventType,
    PolicyStatus,
    ScoringPolicy,
    ScoringPolicyVersion,
)
from pydantic import ValidationError

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
WEIGHTS = {"rules": "0.65", "propensity": "0.35"}
RULES_ONLY_WEIGHTS = {"rules": "1", "ml": "0"}


def test_draft_has_identity_weights_author_and_creation_audit():
    policy = ScoringPolicy.create_draft(
        policy_id="OPP-SCORE-001",
        weights=WEIGHTS,
        author_id="author-1",
        reason="initial policy",
        at=T0,
    )
    version = policy.current
    assert version.policy_id == "OPP-SCORE-001"
    assert version.version == 1
    assert version.status is PolicyStatus.DRAFT
    assert version.weights == {"rules": Decimal("0.65"), "propensity": Decimal("0.35")}
    assert version.author_id == "author-1"
    assert version.audit_events[-1].event_type is PolicyAuditEventType.CREATED
    assert version.audit_events[-1].to_status is PolicyStatus.DRAFT


def test_weights_must_be_non_negative_finite_and_normalized():
    with pytest.raises(ValidationError, match="sum exactly to 1"):
        ScoringPolicyVersion.create_draft(policy_id="P", weights={"a": 0.9}, author_id="u")
    with pytest.raises(ValidationError, match="non-negative"):
        ScoringPolicyVersion.create_draft(
            policy_id="P", weights={"a": -0.1, "b": 1.1}, author_id="u"
        )
    with pytest.raises(ValidationError, match="finite"):
        ScoringPolicyVersion.create_draft(
            policy_id="P", weights={"a": "NaN", "b": 0}, author_id="u"
        )


def test_workflow_is_strict_and_emits_audit_events():
    version = ScoringPolicyVersion.create_draft(
        policy_id="P", weights=RULES_ONLY_WEIGHTS, author_id="author", now=T0
    )
    with pytest.raises(InvalidPolicyTransition):
        version.publish(actor_id="approver", at=T0)

    version = version.simulate(
        actor_id="author", simulation_id="sim-1", at=T0 + timedelta(minutes=1)
    )
    version = version.submit(actor_id="author", at=T0 + timedelta(minutes=2))
    version = version.approve(
        actor_id="approver", reason="reviewed simulation", at=T0 + timedelta(minutes=3)
    )
    version = version.publish(actor_id="approver", at=T0 + timedelta(minutes=4))
    version = version.activate(
        actor_id="operator", effective_from=T0 + timedelta(minutes=5), at=T0 + timedelta(minutes=5)
    )

    assert version.status is PolicyStatus.ACTIVE
    assert version.approver_id == "approver"
    assert version.approval_reason == "reviewed simulation"
    assert [event.event_type for event in version.audit_events] == [
        PolicyAuditEventType.CREATED,
        PolicyAuditEventType.SIMULATED,
        PolicyAuditEventType.SUBMITTED,
        PolicyAuditEventType.APPROVED,
        PolicyAuditEventType.PUBLISHED,
        PolicyAuditEventType.ACTIVATED,
    ]


def test_simulation_requires_persisted_reference_and_author_cannot_approve():
    version = ScoringPolicyVersion.create_draft(
        policy_id="P", weights=WEIGHTS, author_id="same", now=T0
    )
    with pytest.raises(DomainError, match="simulation_id"):
        version.transition(PolicyStatus.SIMULATED, actor_id="same", at=T0)
    version = version.simulate(actor_id="same", simulation_id="sim-1", at=T0)
    version = version.submit(actor_id="same", at=T0)
    with pytest.raises(DomainError, match="author cannot approve"):
        version.approve(actor_id="same", reason="self", at=T0)


def test_approval_requires_reason_and_is_retained_through_publish():
    version = ScoringPolicyVersion.create_draft(
        policy_id="P", weights=WEIGHTS, author_id="a", now=T0
    )
    version = version.simulate(actor_id="a", simulation_id="sim", at=T0)
    version = version.submit(actor_id="a", at=T0)
    with pytest.raises(DomainError, match="approval reason"):
        version.approve(actor_id="b", reason="", at=T0)
    version = version.approve(actor_id="b", reason="four eyes", at=T0)
    assert version.status is PolicyStatus.APPROVED
    assert version.approver_id == "b"
    assert version.approved_at == T0
    assert version.publish(actor_id="b", at=T0).status is PolicyStatus.PUBLISHED


def test_effectivity_window_is_half_open_and_disable_requires_reason():
    version = ScoringPolicyVersion.create_draft(
        policy_id="P", weights=RULES_ONLY_WEIGHTS, author_id="a", now=T0
    )
    version = version.simulate(actor_id="a", simulation_id="sim", at=T0).submit(actor_id="a", at=T0)
    version = version.approve(actor_id="b", reason="review", at=T0).publish(actor_id="b", at=T0)
    start = T0 + timedelta(days=1)
    end = T0 + timedelta(days=2)
    version = version.activate(actor_id="ops", effective_from=start, at=start)
    assert not version.is_effective(start - timedelta(seconds=1))
    assert version.is_effective(start)
    assert version.is_effective(end - timedelta(microseconds=1))
    with pytest.raises(DomainError, match="requires a reason"):
        version.disable(actor_id="ops", reason="", effective_to=end, at=end)
    disabled = version.disable(actor_id="ops", reason="replaced", effective_to=end, at=end)
    assert disabled.status is PolicyStatus.DISABLED
    assert disabled.effective_to == end
    assert not disabled.is_effective(end)


def test_new_version_is_immutable_and_starts_draft():
    policy = ScoringPolicy.create_draft(
        policy_id="P", weights=RULES_ONLY_WEIGHTS, author_id="a", at=T0
    )
    active = policy.transition(PolicyStatus.SIMULATED, actor_id="a", simulation_id="sim", at=T0)
    active = active.transition(PolicyStatus.SUBMITTED, actor_id="a", at=T0)
    active = active.transition(PolicyStatus.APPROVED, actor_id="b", reason="ok", at=T0)
    active = active.transition(PolicyStatus.PUBLISHED, actor_id="b", at=T0)
    active = active.transition(PolicyStatus.ACTIVE, actor_id="ops", at=T0)
    next_policy = active.add_version(
        weights={"rules": 0.5, "propensity": 0.5},
        author_id="new-author",
        reason="new calibration",
        at=T0,
    )
    assert active.current.status is PolicyStatus.ACTIVE
    assert next_policy.current.version == 2
    assert next_policy.current.status is PolicyStatus.DRAFT
    assert next_policy.active_version == 1


def test_aggregate_rollback_disables_current_and_reactivates_target_without_rewriting_history():
    policy = ScoringPolicy.create_draft(
        policy_id="P", weights=RULES_ONLY_WEIGHTS, author_id="a", at=T0
    )
    policy = policy.transition(PolicyStatus.SIMULATED, actor_id="a", simulation_id="sim-1", at=T0)
    policy = policy.transition(PolicyStatus.SUBMITTED, actor_id="a", at=T0)
    policy = policy.transition(PolicyStatus.APPROVED, actor_id="b", reason="review 1", at=T0)
    policy = policy.transition(PolicyStatus.PUBLISHED, actor_id="b", at=T0)
    policy = policy.transition(PolicyStatus.ACTIVE, actor_id="ops", at=T0)
    policy = policy.add_version(weights=RULES_ONLY_WEIGHTS, author_id="a", at=T0)
    policy = policy.transition(PolicyStatus.SIMULATED, actor_id="a", simulation_id="sim-2", at=T0)
    policy = policy.transition(PolicyStatus.SUBMITTED, actor_id="a", at=T0)
    policy = policy.transition(PolicyStatus.APPROVED, actor_id="c", reason="review 2", at=T0)
    policy = policy.transition(PolicyStatus.PUBLISHED, actor_id="c", at=T0)
    policy = policy.transition(PolicyStatus.ACTIVE, actor_id="ops", at=T0)

    rolled_back = policy.rollback(
        target_version=1, actor_id="ops", reason="regression detected", at=T0 + timedelta(days=1)
    )
    assert rolled_back.active_version == 1
    assert rolled_back.version(1).status is PolicyStatus.ACTIVE
    assert rolled_back.version(2).status is PolicyStatus.ROLLED_BACK
    assert rolled_back.audit_events[-1].event_type is PolicyAuditEventType.ROLLBACK_ACTIVATED
    assert rolled_back.audit_events[-1].metadata["targetVersion"] == 1
    assert any(
        event.event_type is PolicyAuditEventType.ROLLED_BACK
        for event in rolled_back.version(2).audit_events
    )


def test_rollback_rejects_unknown_or_current_target():
    policy = ScoringPolicy.create_draft(policy_id="P", weights=WEIGHTS, author_id="a", at=T0)
    with pytest.raises(DomainError, match="current version"):
        policy.rollback(target_version=1, actor_id="ops", reason="no-op", at=T0)
    with pytest.raises(DomainError, match="unknown"):
        policy.rollback(target_version=9, actor_id="ops", reason="missing", at=T0)


def test_hybrid_policy_can_be_simulated_but_not_activated_without_boa_labels():
    version = ScoringPolicyVersion.create_draft(
        policy_id="P", weights=WEIGHTS, author_id="a", now=T0
    )
    version = version.simulate(actor_id="a", simulation_id="sim", at=T0)
    version = version.submit(actor_id="a", at=T0)
    version = version.approve(actor_id="b", reason="review", at=T0)
    version = version.publish(actor_id="b", at=T0)
    with pytest.raises(DomainError, match="RULES_ONLY"):
        version.activate(actor_id="ops", at=T0)


def test_model_is_frozen_and_policy_history_matches_policy_id():
    version = ScoringPolicyVersion.create_draft(
        policy_id="P", weights=WEIGHTS, author_id="a", now=T0
    )
    with pytest.raises(ValidationError):
        version.status = PolicyStatus.ACTIVE
    with pytest.raises(ValidationError, match="policy_id"):
        ScoringPolicy(policyId="P", versions=(version.model_copy(update={"policy_id": "OTHER"}),))
