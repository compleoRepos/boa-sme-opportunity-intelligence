from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .monitoring import AuditEvent, Severity


class ReadinessStatus(str, Enum):
    NOT_READY = "NOT_READY"
    READY_FOR_SHADOW = "READY_FOR_SHADOW"
    READY_FOR_PRODUCTION = "READY_FOR_PRODUCTION"


@dataclass(frozen=True)
class ObservabilityEvent:
    trace_id: str
    service: str
    endpoint: str
    status: str | int
    latency: float
    model_version: str | None = None
    scoring_policy_version: str | None = None
    fallback_mode: str = "NONE"
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        required = (self.trace_id, self.service, self.endpoint, self.fallback_mode)
        if any(not str(value).strip() for value in required):
            raise ValueError("trace_id, service, endpoint, and fallback_mode are required")
        if self.latency < 0:
            raise ValueError("latency cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "traceId": self.trace_id,
            "service": self.service,
            "endpoint": self.endpoint,
            "status": self.status,
            "latency": self.latency,
            "modelVersion": self.model_version,
            "scoringPolicyVersion": self.scoring_policy_version,
            "fallbackMode": self.fallback_mode,
            "recordedAt": self.recorded_at.isoformat(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ObservabilityEvent:
        return cls(
            trace_id=str(value["traceId"] if "traceId" in value else value["trace_id"]),
            service=str(value["service"]),
            endpoint=str(value["endpoint"]),
            status=value["status"],
            latency=float(value["latency"]),
            model_version=value.get("modelVersion", value.get("model_version")),
            scoring_policy_version=value.get(
                "scoringPolicyVersion", value.get("scoring_policy_version")
            ),
            fallback_mode=str(value.get("fallbackMode", value.get("fallback_mode", "NONE"))),
            recorded_at=datetime.fromisoformat(value["recordedAt"])
            if value.get("recordedAt")
            else datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class ReadinessComponent:
    name: str
    required: bool = True
    passed: bool = False
    evidence: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "passed": self.passed,
            "status": self.status,
            "evidence": self.evidence,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ReadinessReport:
    status: ReadinessStatus
    components: tuple[ReadinessComponent, ...]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def blocking_components(self) -> tuple[ReadinessComponent, ...]:
        return tuple(
            component
            for component in self.components
            if component.required and not component.passed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "components": [component.to_dict() for component in self.components],
            "blockingComponents": [component.name for component in self.blocking_components],
            "generatedAt": self.generated_at.isoformat(),
        }


DEFAULT_COMPONENTS = (
    "contracts",
    "historical_data",
    "model_validation",
    "feature_lineage",
    "drift_monitoring",
    "operational_monitoring",
    "rules_only_fallback",
    "structured_audit",
    "observability",
    "rollback",
    "approval",
)


class ReadinessAggregator:
    """Pure readiness calculation; no component is inferred from a missing value."""

    def __init__(self, required_components: tuple[str, ...] = DEFAULT_COMPONENTS) -> None:
        self.required_components = required_components

    def evaluate(
        self,
        components: Mapping[str, bool | ReadinessComponent],
        *,
        requested_status: ReadinessStatus | str = ReadinessStatus.READY_FOR_PRODUCTION,
    ) -> ReadinessReport:
        requested = ReadinessStatus(requested_status)
        normalized = tuple(
            value
            if isinstance(value, ReadinessComponent)
            else ReadinessComponent(name=name, passed=bool(value))
            for name, value in (
                (name, components.get(name, False)) for name in self.required_components
            )
        )
        blocking = any(component.required and not component.passed for component in normalized)
        if blocking:
            status = ReadinessStatus.NOT_READY
        elif requested is ReadinessStatus.READY_FOR_PRODUCTION:
            status = ReadinessStatus.READY_FOR_PRODUCTION
        else:
            status = requested
        return ReadinessReport(status, normalized)

    def from_evidence(
        self,
        evidence: Mapping[str, Any],
        *,
        requested_status: ReadinessStatus | str = ReadinessStatus.READY_FOR_PRODUCTION,
    ) -> ReadinessReport:
        """Build a report only from explicit evidence.

        Missing prerequisites default to failure.
        """
        components: dict[str, ReadinessComponent] = {}
        for name in self.required_components:
            value = evidence.get(name)
            if isinstance(value, ReadinessComponent):
                components[name] = value
            elif isinstance(value, Mapping):
                components[name] = ReadinessComponent(
                    name=name,
                    required=bool(value.get("required", True)),
                    passed=bool(value.get("passed", False)),
                    evidence=value.get("evidence"),
                    details=value,
                )
            else:
                components[name] = ReadinessComponent(name=name, passed=value is True)
        return self.evaluate(components, requested_status=requested_status)


def production_readiness(*, components: Mapping[str, bool | ReadinessComponent]) -> ReadinessReport:
    return ReadinessAggregator().evaluate(
        components, requested_status=ReadinessStatus.READY_FOR_PRODUCTION
    )


def audit_event(
    event_type: str,
    subject: str,
    status: Severity | str,
    payload: Mapping[str, Any],
    *,
    trace_id: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_type=event_type,
        subject=subject,
        status=status,
        payload=dict(payload),
        trace_id=trace_id,
    )


__all__ = [
    "DEFAULT_COMPONENTS",
    "ObservabilityEvent",
    "ReadinessAggregator",
    "ReadinessComponent",
    "ReadinessReport",
    "ReadinessStatus",
    "audit_event",
    "production_readiness",
]
