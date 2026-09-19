from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from boa_oi.models.entities import (
    Rule,
    RuleAction,
    RuleApproval,
    RuleAuditLog,
    RuleCondition,
    RuleConfidenceConfiguration,
    RuleSimulation,
    RuleVersion,
)
from boa_oi.platform import Problem, not_found
from boa_oi.rules.domain import canonical_operator, validate_rule_definition

STATUS_SEQUENCE = (
    "DRAFT",
    "VALIDATED",
    "SIMULATED",
    "SUBMITTED",
    "APPROVED",
    "PUBLISHED",
    "ACTIVE",
)
TRANSITIONS = {
    "validate": ("DRAFT", "VALIDATED"),
    "simulate": ("VALIDATED", "SIMULATED"),
    "submit": ("SIMULATED", "SUBMITTED"),
    "approve": ("SUBMITTED", "APPROVED"),
    "publish": ("APPROVED", "PUBLISHED"),
    "activate": ("PUBLISHED", "ACTIVE"),
    "disable": ("ACTIVE", "DISABLED"),
    "retire": ("ACTIVE", "RETIRED"),
}
AUDIT_ACTIONS = {
    "validate": "VALIDATED",
    "simulate": "SIMULATED",
    "submit": "SUBMITTED",
    "approve": "APPROVED",
    "publish": "PUBLISHED",
    "activate": "ACTIVATED",
    "disable": "DISABLED",
    "retire": "RETIRED",
}


def _checksum(definition: dict[str, Any]) -> str:
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _score(value: Any) -> Decimal:
    number = Decimal(str(value or 0))
    return number / Decimal(100) if abs(number) > 1 else number


def _condition_nodes(definition: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(
        node: dict[str, Any], path: str, position: int, parent_token: str | None = None
    ) -> None:
        children = node.get("conditions")
        if children is not None:
            result.append(
                {
                    "token": path,
                    "parent": parent_token,
                    "path": path,
                    "position": position,
                    "node_type": "GROUP",
                    "logic": str(node.get("logic", node.get("operator", "AND"))).upper(),
                    "metric_code": None,
                    "operator": None,
                    "value_json": None,
                    "unit": None,
                    "period": None,
                }
            )
            for index, child in enumerate(children):
                visit(child, f"{path}.{index}", index, path)
            return
        result.append(
            {
                "token": path,
                "parent": parent_token,
                "path": path,
                "position": position,
                "node_type": "CONDITION",
                "logic": None,
                "metric_code": str(node["metric"]),
                "operator": canonical_operator(str(node["operator"])),
                "value_json": node.get("value"),
                "unit": node.get("unit"),
                "period": node.get("period"),
            }
        )

    visit(
        {"logic": definition.get("logic", "AND"), "conditions": definition["conditions"]},
        "root",
        0,
    )
    return result


def latest_version(session: Session, rule: Rule) -> RuleVersion:
    version = session.scalar(
        select(RuleVersion).where(
            RuleVersion.rule_id == rule.id,
            RuleVersion.version == rule.current_version,
        )
    )
    if version is None:
        raise Problem(500, "RULE_VERSION_MISSING", "The current rule version is missing.")
    return version


def active_versions(session: Session) -> list[tuple[Rule, RuleVersion]]:
    rows = session.execute(
        select(Rule, RuleVersion)
        .join(RuleVersion, RuleVersion.rule_id == Rule.id)
        .where(
            Rule.status == "ACTIVE",
            RuleVersion.status == "ACTIVE",
            Rule.active_version == RuleVersion.version,
        )
        .order_by(Rule.rule_id)
    )
    return [(row[0], row[1]) for row in rows]


def find_rule(session: Session, rule_id: str, *, lock: bool = False) -> Rule:
    stmt = select(Rule).where(Rule.rule_id == rule_id)
    if lock:
        stmt = stmt.with_for_update()
    rule = session.scalar(stmt)
    if rule is None:
        raise not_found("Rule")
    return rule


def audit(
    session: Session,
    rule: Rule,
    version: int,
    action: str,
    actor: str,
    *,
    old: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
    reason: str | None = None,
) -> RuleAuditLog:
    record = RuleAuditLog(
        id=uuid4(),
        rule_id=rule.id,
        rule_version=version,
        action=action,
        user_id=actor,
        timestamp=datetime.now(timezone.utc),
        old_value_json=old,
        new_value_json=new,
        reason=reason,
    )
    session.add(record)
    return record


def persist_definition(
    session: Session,
    rule: Rule,
    *,
    version_number: int,
    definition: dict[str, Any],
    actor: str,
    status: str = "DRAFT",
) -> RuleVersion:
    version = RuleVersion(
        id=uuid4(),
        rule_id=rule.id,
        version=version_number,
        status=status,
        name=str(definition["name"]),
        description=str(definition.get("description", "")),
        scope_json=dict(definition.get("scope") or {}),
        logic=str(definition.get("logic", "AND")).upper(),
        configuration_json=definition,
        checksum=_checksum(definition),
        created_at=datetime.now(timezone.utc),
        created_by=actor,
    )
    session.add(version)
    session.flush()
    ids: dict[str, UUID] = {}
    nodes = _condition_nodes(definition)
    for item in nodes:
        node_id = uuid4()
        ids[item["token"]] = node_id
        session.add(
            RuleCondition(
                id=node_id,
                rule_version_id=version.id,
                parent_condition_id=ids.get(item["parent"]),
                path=item["path"],
                position=item["position"],
                node_type=item["node_type"],
                logic=item["logic"],
                metric_code=item["metric_code"],
                operator=item["operator"],
                value_json=item["value_json"],
                unit=item["unit"],
                period=item["period"],
            )
        )
    recommendation = definition["recommendation"]
    session.add(
        RuleAction(
            id=uuid4(),
            rule_version_id=version.id,
            position=0,
            opportunity_type_code=recommendation["opportunityType"],
            product_codes_json=list(recommendation.get("products") or []),
            horizon_code=recommendation.get("horizon"),
        )
    )
    confidence = definition.get("confidence") or {}
    session.add(
        RuleConfidenceConfiguration(
            id=uuid4(),
            rule_version_id=version.id,
            base_score=_score(confidence.get("baseScore", 0)),
            weights_json=dict(confidence.get("weights") or {}),
        )
    )
    return version


def create_rule(session: Session, definition: dict[str, Any], actor: str) -> Rule:
    definition = dict(definition)
    reason = definition.pop("reason", None)
    errors = validate_rule_definition(definition)
    if errors:
        raise Problem(
            422,
            "RULE_VALIDATION_FAILED",
            "The rule definition is invalid.",
            details=[{"field": "rule", "code": "INVALID_RULE", "message": item} for item in errors],
        )
    supplied_id = definition.get("ruleId")
    rule_id = str(supplied_id or f"RULE-{uuid4().hex[:12].upper()}")
    if session.scalar(select(Rule.id).where(Rule.rule_id == rule_id)):
        raise Problem(409, "RULE_ALREADY_EXISTS", "A rule with this ruleId already exists.")
    rule = Rule(
        id=uuid4(),
        rule_id=rule_id,
        name=str(definition["name"]),
        description=str(definition.get("description", "")),
        status="DRAFT",
        current_version=1,
        active_version=None,
        created_by=actor,
    )
    session.add(rule)
    session.flush()
    payload = dict(definition)
    payload["ruleId"] = rule_id
    payload["version"] = 1
    payload["status"] = "DRAFT"
    persist_definition(session, rule, version_number=1, definition=payload, actor=actor)
    audit(session, rule, 1, "CREATED", actor, new=payload, reason=reason)
    return rule


def update_rule(session: Session, rule_id: str, definition: dict[str, Any], actor: str) -> Rule:
    definition = dict(definition)
    reason = definition.pop("reason", None)
    rule = find_rule(session, rule_id, lock=True)
    if rule.status in {"SUBMITTED", "APPROVED", "PUBLISHED"}:
        raise Problem(409, "RULE_LOCKED", "A rule in approval or publication cannot be modified.")
    errors = validate_rule_definition(definition)
    if errors:
        raise Problem(
            422,
            "RULE_VALIDATION_FAILED",
            "The rule definition is invalid.",
            details=[{"field": "rule", "code": "INVALID_RULE", "message": item} for item in errors],
        )
    old_version = latest_version(session, rule)
    next_version = rule.current_version + 1
    payload = dict(definition)
    payload["ruleId"] = rule.rule_id
    payload["version"] = next_version
    payload["status"] = "DRAFT"
    persist_definition(
        session,
        rule,
        version_number=next_version,
        definition=payload,
        actor=actor,
    )
    old = old_version.configuration_json
    rule.name = str(payload["name"])
    rule.description = str(payload.get("description", ""))
    rule.current_version = next_version
    rule.status = "DRAFT"
    audit(session, rule, next_version, "UPDATED", actor, old=old, new=payload, reason=reason)
    return rule


def duplicate_rule(
    session: Session, rule_id: str, name: str, actor: str, reason: str | None = None
) -> Rule:
    source = latest_version(session, find_rule(session, rule_id))
    payload = dict(source.configuration_json)
    for generated_field in ("ruleId", "version", "status"):
        payload.pop(generated_field, None)
    payload["name"] = name
    payload["reason"] = reason or f"Duplicated from {rule_id}"
    return create_rule(session, payload, actor)


def transition(
    session: Session,
    rule_id: str,
    event: str,
    actor: str,
    *,
    reason: str | None = None,
) -> Rule:
    rule = find_rule(session, rule_id, lock=True)
    current, target = TRANSITIONS[event]
    if rule.status != current:
        raise Problem(
            409,
            "INVALID_RULE_TRANSITION",
            f"{event} requires {current}; the rule is {rule.status}.",
        )
    version = latest_version(session, rule)
    if event == "validate":
        errors = validate_rule_definition(version.configuration_json)
        if errors:
            raise Problem(
                422,
                "RULE_VALIDATION_FAILED",
                "The rule definition is invalid.",
                details=[
                    {"field": "rule", "code": "INVALID_RULE", "message": item} for item in errors
                ],
            )
    if event == "simulate":
        simulation = session.scalar(
            select(RuleSimulation.id).where(RuleSimulation.rule_version_id == version.id).limit(1)
        )
        if simulation is None:
            raise Problem(409, "SIMULATION_REQUIRED", "A persisted simulation is required.")
    if event == "approve":
        if version.created_by == actor:
            raise Problem(
                403,
                "SELF_APPROVAL_FORBIDDEN",
                "A rule creator cannot approve the same rule version.",
            )
        session.add(
            RuleApproval(
                id=uuid4(),
                rule_version_id=version.id,
                decision="APPROVED",
                actor_subject_id=actor,
                reason=reason,
                decided_at=datetime.now(timezone.utc),
            )
        )
    if event == "submit":
        session.add(
            RuleApproval(
                id=uuid4(),
                rule_version_id=version.id,
                decision="SUBMITTED",
                actor_subject_id=actor,
                reason=reason,
                decided_at=datetime.now(timezone.utc),
            )
        )
    old = {"status": rule.status}
    rule.status = target
    version.status = target
    if event == "activate":
        previous = list(
            session.scalars(
                select(RuleVersion).where(
                    RuleVersion.rule_id == rule.id,
                    RuleVersion.status == "ACTIVE",
                    RuleVersion.id != version.id,
                )
            )
        )
        for item in previous:
            item.status = "RETIRED"
        rule.active_version = version.version
    if event == "disable":
        rule.disabled_reason = reason
    payload = dict(version.configuration_json)
    payload["status"] = target
    version.configuration_json = payload
    audit(
        session,
        rule,
        version.version,
        AUDIT_ACTIONS[event],
        actor,
        old=old,
        new={"status": target},
        reason=reason,
    )
    return rule


def rollback_rule(
    session: Session,
    rule_id: str,
    actor: str,
    *,
    target_version: int,
    reason: str | None = None,
) -> Rule:
    rule = find_rule(session, rule_id, lock=True)
    if rule.status in {"SUBMITTED", "APPROVED", "PUBLISHED"}:
        raise Problem(409, "RULE_LOCKED", "The current approval workflow must complete first.")
    source = session.scalar(
        select(RuleVersion).where(
            RuleVersion.rule_id == rule.id,
            RuleVersion.version == target_version,
        )
    )
    if source is None:
        raise not_found("Rule version")
    old = latest_version(session, rule).configuration_json
    next_version = rule.current_version + 1
    payload = dict(source.configuration_json)
    payload["version"] = next_version
    payload["status"] = "DRAFT"
    persist_definition(
        session,
        rule,
        version_number=next_version,
        definition=payload,
        actor=actor,
    )
    rule.current_version = next_version
    rule.status = "DRAFT"
    rule.name = str(payload["name"])
    rule.description = str(payload.get("description", ""))
    audit(
        session,
        rule,
        next_version,
        "ROLLED_BACK",
        actor,
        old=old,
        new=payload,
        reason=reason or f"Restored from version {target_version}",
    )
    return rule


def serialize_version(version: RuleVersion) -> dict[str, Any]:
    result = dict(version.configuration_json)
    result.setdefault(
        "lifecycle",
        {
            "validityDays": 90,
            "dismissedCooldownDays": 30,
            "convertedCooldownDays": 180,
            "deferredCooldownDays": 30,
            "expiredCooldownDays": 7,
        },
    )
    result.update(
        {
            "version": version.version,
            "status": version.status,
            "checksum": version.checksum,
            "createdAt": version.created_at.isoformat(),
            "createdBy": version.created_by,
        }
    )
    return result


def serialize_rule(session: Session, rule: Rule) -> dict[str, Any]:
    version = latest_version(session, rule)
    result = serialize_version(version)
    result.update(
        {
            "ruleId": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "status": rule.status,
            "version": rule.current_version,
            "activeVersion": rule.active_version,
            "createdBy": rule.created_by,
            "createdAt": rule.created_at.isoformat(),
            "updatedAt": rule.updated_at.isoformat(),
        }
    )
    return result


def delete_version_children(session: Session, version_id: UUID) -> None:
    """Maintenance helper kept private; audit rows are deliberately never deleted."""
    for model in (RuleConfidenceConfiguration, RuleAction, RuleCondition):
        session.execute(delete(model).where(model.rule_version_id == version_id))


__all__ = [
    "STATUS_SEQUENCE",
    "active_versions",
    "audit",
    "create_rule",
    "duplicate_rule",
    "find_rule",
    "latest_version",
    "persist_definition",
    "rollback_rule",
    "serialize_rule",
    "serialize_version",
    "transition",
    "update_rule",
]
