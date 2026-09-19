from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @classmethod
    def worst(cls, *values: Severity | str) -> Severity:
        levels = {cls.OK: 0, cls.WARNING: 1, cls.CRITICAL: 2}
        return max((cls(value) for value in values), key=levels.__getitem__, default=cls.OK)


class DriftDomain(str, Enum):
    DATA = "DATA"
    FEATURE = "FEATURE"
    PREDICTION = "PREDICTION"


@dataclass(frozen=True)
class Thresholds:
    """A monotonically increasing WARNING/CRITICAL threshold pair."""

    warning: float
    critical: float

    def __post_init__(self) -> None:
        if not all(isfinite(float(value)) for value in (self.warning, self.critical)):
            raise ValueError("thresholds must be finite numbers")
        if float(self.warning) < 0 or float(self.critical) < 0:
            raise ValueError("thresholds must be non-negative")
        if float(self.warning) > float(self.critical):
            raise ValueError("warning threshold cannot exceed critical threshold")

    def classify(self, value: float) -> Severity:
        value = float(value)
        if not isfinite(value):
            raise ValueError("metric value must be finite")
        if value >= self.critical:
            return Severity.CRITICAL
        if value >= self.warning:
            return Severity.WARNING
        return Severity.OK

    def to_dict(self) -> dict[str, float]:
        return {"WARNING": float(self.warning), "CRITICAL": float(self.critical)}


@dataclass(frozen=True)
class LowerBoundThresholds:
    """Minimum acceptable value; critical is the lower (more severe) bound."""

    warning: float
    critical: float

    def __post_init__(self) -> None:
        if not all(isfinite(float(value)) for value in (self.warning, self.critical)):
            raise ValueError("thresholds must be finite numbers")
        if float(self.warning) < 0 or float(self.critical) < 0:
            raise ValueError("thresholds must be non-negative")
        if float(self.warning) < float(self.critical):
            raise ValueError("warning lower bound cannot be below critical lower bound")

    def classify(self, value: float) -> Severity:
        if not isfinite(float(value)):
            raise ValueError("metric value must be finite")
        if value < self.critical:
            return Severity.CRITICAL
        if value < self.warning:
            return Severity.WARNING
        return Severity.OK

    def to_dict(self) -> dict[str, float]:
        return {"WARNING": float(self.warning), "CRITICAL": float(self.critical)}


@dataclass(frozen=True)
class DriftThresholds(Thresholds):
    """Thresholds for a drift score (PSI, distance, unknown-rate, etc.)."""

    method: str = "unspecified"
    reference_version: str = "unspecified"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> DriftThresholds:
        return cls(
            warning=float(value.get("warning", value.get("WARNING", 0.1))),
            critical=float(value.get("critical", value.get("CRITICAL", 0.2))),
            method=str(value.get("method", "unspecified")),
            reference_version=str(
                value.get("referenceVersion", value.get("reference_version", "unspecified"))
            ),
        )


@dataclass(frozen=True)
class DriftObservation:
    domain: DriftDomain
    metric: str
    value: float
    thresholds: DriftThresholds
    segment: str = "ALL"
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sample_size: int | None = None
    reference_version: str | None = None
    population: str | None = None

    @property
    def severity(self) -> Severity:
        return self.thresholds.classify(self.value)

    @property
    def is_blocking(self) -> bool:
        return self.severity is Severity.CRITICAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "metric": self.metric,
            "value": float(self.value),
            "severity": self.severity.value,
            "segment": self.segment,
            "observedAt": self.observed_at.isoformat(),
            "sampleSize": self.sample_size,
            "referenceVersion": self.reference_version or self.thresholds.reference_version,
            "population": self.population,
            "method": self.thresholds.method,
            "thresholds": self.thresholds.to_dict(),
        }


@dataclass(frozen=True)
class RulesOnlyRate:
    rules_only_count: int
    total_count: int
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.rules_only_count < 0 or self.total_count < 0:
            raise ValueError("counts must be non-negative")
        if self.rules_only_count > self.total_count:
            raise ValueError("rules-only count cannot exceed total count")

    @property
    def rate(self) -> float:
        return self.rules_only_count / self.total_count if self.total_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rulesOnlyCount": self.rules_only_count,
            "totalCount": self.total_count,
            "rulesOnlyRate": self.rate,
            "observedAt": self.observed_at.isoformat(),
        }


def rules_only_rate(rules_only_count: int, total_count: int) -> float:
    return RulesOnlyRate(rules_only_count, total_count).rate


@dataclass(frozen=True)
class OperationalThresholds:
    """Upper bounds for latency/errors and a lower bound for accepted volume."""

    latency_ms: Thresholds = field(default_factory=lambda: Thresholds(500.0, 2_000.0))
    error_rate: Thresholds = field(default_factory=lambda: Thresholds(0.01, 0.05))
    volume: LowerBoundThresholds = field(default_factory=lambda: LowerBoundThresholds(1.0, 1.0))
    rules_only_rate: Thresholds = field(default_factory=lambda: Thresholds(0.20, 0.50))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> OperationalThresholds:
        def pair(name: str, default: Thresholds) -> Thresholds:
            raw = value.get(name, value.get(_camel(name)))
            if raw is None:
                return default
            if isinstance(raw, Thresholds):
                return raw
            if isinstance(raw, Mapping):
                return Thresholds(
                    float(raw.get("warning", raw.get("WARNING", default.warning))),
                    float(raw.get("critical", raw.get("CRITICAL", default.critical))),
                )
            raise TypeError(f"{name} thresholds must be a mapping or Thresholds")

        return cls(
            latency_ms=pair("latency_ms", cls().latency_ms),
            error_rate=pair("error_rate", cls().error_rate),
            volume=LowerBoundThresholds(
                float(
                    (value.get("volume", value.get("volumeThresholds", {}))).get(
                        "warning", cls().volume.warning
                    )
                ),
                float(
                    (value.get("volume", value.get("volumeThresholds", {}))).get(
                        "critical", cls().volume.critical
                    )
                ),
            )
            if isinstance(value.get("volume", value.get("volumeThresholds", {})), Mapping)
            else cls().volume,
            rules_only_rate=pair("rules_only_rate", cls().rules_only_rate),
        )


@dataclass(frozen=True)
class OperationalMetrics:
    latency_ms: float
    errors: int = 0
    requests: int = 0
    volume: int = 0
    rules_only_count: int = 0
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name in ("errors", "requests", "volume", "rules_only_count"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.errors > self.requests and self.requests:
            raise ValueError("errors cannot exceed requests")
        if self.rules_only_count > self.requests:
            raise ValueError("rules-only count cannot exceed requests")

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0

    @property
    def rules_only_rate(self) -> float:
        return self.rules_only_count / self.requests if self.requests else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "latencyMs": float(self.latency_ms),
            "errors": self.errors,
            "requests": self.requests,
            "volume": self.volume,
            "errorRate": self.error_rate,
            "rulesOnlyCount": self.rules_only_count,
            "rulesOnlyRate": self.rules_only_rate,
            "observedAt": self.observed_at.isoformat(),
        }


@dataclass(frozen=True)
class OperationalObservation:
    metrics: OperationalMetrics
    thresholds: OperationalThresholds

    @property
    def severities(self) -> Mapping[str, Severity]:
        # Volume is a lower-bound metric: a volume below CRITICAL/WARNING is bad.
        volume = self.thresholds.volume.classify(self.metrics.volume)
        return MappingProxyType(
            {
                "latency": self.thresholds.latency_ms.classify(self.metrics.latency_ms),
                "errorRate": self.thresholds.error_rate.classify(self.metrics.error_rate),
                "volume": volume,
                "rulesOnlyRate": self.thresholds.rules_only_rate.classify(
                    self.metrics.rules_only_rate
                ),
            }
        )

    @property
    def severity(self) -> Severity:
        return Severity.worst(*self.severities.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.metrics.to_dict(),
            "severity": self.severity.value,
            "severities": {name: severity.value for name, severity in self.severities.items()},
            "thresholds": {
                "latencyMs": self.thresholds.latency_ms.to_dict(),
                "errorRate": self.thresholds.error_rate.to_dict(),
                "volume": self.thresholds.volume.to_dict(),
                "rulesOnlyRate": self.thresholds.rules_only_rate.to_dict(),
            },
        }


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    subject: str
    status: Severity | str
    payload: Mapping[str, Any]
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value if isinstance(self.status, Enum) else str(self.status)
        return {
            "eventType": self.event_type,
            "subject": self.subject,
            "status": status,
            "payload": dict(self.payload),
            "recordedAt": self.recorded_at.isoformat(),
            "traceId": self.trace_id,
        }


class MonitoringHistory:
    """Bounded in-memory history; persistence is deliberately left to an adapter."""

    def __init__(self, max_entries: int = 1_000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: list[DriftObservation | OperationalObservation | AuditEvent] = []

    def append(self, entry: DriftObservation | OperationalObservation | AuditEvent) -> None:
        self._entries.append(entry)
        del self._entries[: -self._max_entries]

    def all(self) -> tuple[DriftObservation | OperationalObservation | AuditEvent, ...]:
        return tuple(self._entries)

    def clear(self) -> None:
        self._entries.clear()


class DriftMonitor:
    def __init__(
        self,
        thresholds: Mapping[DriftDomain | str, DriftThresholds] | None = None,
        history: MonitoringHistory | None = None,
    ) -> None:
        self.thresholds = {DriftDomain(key): value for key, value in (thresholds or {}).items()}
        self.history = history or MonitoringHistory()

    def observe(
        self,
        domain: DriftDomain | str,
        metric: str,
        value: float,
        *,
        segment: str = "ALL",
        sample_size: int | None = None,
        reference_version: str | None = None,
        population: str | None = None,
        thresholds: DriftThresholds | None = None,
    ) -> DriftObservation:
        resolved = thresholds or self.thresholds.get(DriftDomain(domain))
        if resolved is None:
            raise ValueError(f"no thresholds configured for {DriftDomain(domain).value} drift")
        observation = DriftObservation(
            DriftDomain(domain),
            metric,
            float(value),
            resolved,
            segment,
            sample_size=sample_size,
            reference_version=reference_version,
            population=population,
        )
        self.history.append(observation)
        return observation

    record = observe

    def latest(self, domain: DriftDomain | str | None = None) -> tuple[DriftObservation, ...]:
        entries = [entry for entry in self.history.all() if isinstance(entry, DriftObservation)]
        if domain is not None:
            entries = [entry for entry in entries if entry.domain is DriftDomain(domain)]
        return tuple(entries)


class OperationalMonitor:
    def __init__(
        self,
        thresholds: OperationalThresholds | None = None,
        history: MonitoringHistory | None = None,
    ) -> None:
        self.thresholds = thresholds or OperationalThresholds()
        self.history = history or MonitoringHistory()

    def observe(
        self, metrics: OperationalMetrics | None = None, **values: Any
    ) -> OperationalObservation:
        observation = OperationalObservation(
            metrics or OperationalMetrics(**values), self.thresholds
        )
        self.history.append(observation)
        return observation

    record = observe


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


__all__ = [
    "AuditEvent",
    "DriftDomain",
    "DriftMonitor",
    "DriftObservation",
    "DriftThresholds",
    "LowerBoundThresholds",
    "MonitoringHistory",
    "OperationalMetrics",
    "OperationalMonitor",
    "OperationalObservation",
    "OperationalThresholds",
    "RulesOnlyRate",
    "Severity",
    "Thresholds",
    "rules_only_rate",
]

# Friendly aliases for callers that use metric terminology.
DriftSeverity = Severity
OperationalMetricSnapshot = OperationalMetrics
ThresholdConfig = Thresholds
