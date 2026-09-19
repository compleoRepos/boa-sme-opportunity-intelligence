from __future__ import annotations

import asyncio
import inspect
import math
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any


class FallbackMode(StrEnum):
    HYBRID_ML = "HYBRID_ML"
    RULES_ONLY = "RULES_ONLY"


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CauseCategory(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    CIRCUIT = "CIRCUIT"
    TIMEOUT = "TIMEOUT"
    HTTP = "HTTP"
    NETWORK = "NETWORK"
    SCORE = "SCORE"


@dataclass(frozen=True, slots=True)
class FallbackCause:
    """Machine-readable reason for using rules instead of an ML score."""

    code: str
    category: CauseCategory | str
    message: str
    retryable: bool = False
    status_code: int | None = None
    attempts: int = 0
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": str(self.category),
            "message": self.message,
            "retryable": self.retryable,
            "statusCode": self.status_code,
            "attempts": self.attempts,
            "details": dict(self.details),
        }

    to_dict = as_dict


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Serializable audit record emitted for every ML decision attempt."""

    event_type: str
    occurred_at: str
    mode: FallbackMode
    circuit_state: CircuitState
    cause: FallbackCause | None
    attempts: int
    score_present: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "eventType": self.event_type,
            "occurredAt": self.occurred_at,
            "mode": self.mode.value,
            "circuitState": self.circuit_state.value,
            "cause": self.cause.as_dict() if self.cause else None,
            "attempts": self.attempts,
            "scorePresent": self.score_present,
            "metadata": dict(self.metadata),
        }

    to_dict = as_dict


@dataclass(frozen=True, slots=True)
class MLScoreResult:
    """Result contract: score is None on every fallback; no previous score is retained."""

    score: float | None
    mode: FallbackMode
    used_ml: bool
    cause: FallbackCause | None
    audit_event: AuditEvent
    attempts: int
    circuit_state: CircuitState
    response: Mapping[str, Any] | None = None

    @property
    def ml_score(self) -> float | None:
        return self.score

    @property
    def propensity(self) -> float | None:
        return self.score

    @property
    def rules_only(self) -> bool:
        return self.mode is FallbackMode.RULES_ONLY

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "mlScore": self.score,
            "mode": self.mode.value,
            "usedMl": self.used_ml,
            "cause": self.cause.as_dict() if self.cause else None,
            "auditEvent": self.audit_event.as_dict(),
            "attempts": self.attempts,
            "circuitState": self.circuit_state.value,
        }

    to_dict = as_dict


# Backward/consumer-friendly aliases; the implementation has one result contract.
MLClientResult = MLScoreResult
StructuredCause = FallbackCause
ResilienceAuditEvent = AuditEvent


class CircuitBreaker:
    """Small process-local circuit breaker; it deliberately has no persistence or score cache."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if recovery_timeout <= 0 or not math.isfinite(recovery_timeout):
            raise ValueError("recovery_timeout must be finite and positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = float(recovery_timeout)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe = False
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._refresh_locked(self._clock())
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked(self._clock())
            return {
                "state": self._state.value,
                "failureCount": self._failure_count,
                "openedAt": self._opened_at,
                "halfOpenProbe": self._half_open_probe,
            }

    def allow_request(self, now: float | None = None) -> bool:
        """Allow normal calls in CLOSED and one probe in HALF_OPEN."""
        with self._lock:
            current = self._clock() if now is None else now
            self._refresh_locked(current)
            if self._state is CircuitState.OPEN:
                return False
            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_probe:
                    return False
                self._half_open_probe = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_probe = False

    def record_failure(self, now: float | None = None) -> None:
        with self._lock:
            current = self._clock() if now is None else now
            self._refresh_locked(current)
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = current
                self._half_open_probe = False
                return
            self._failure_count += 1
            self._half_open_probe = False
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = current

    def reset(self) -> None:
        self.record_success()

    def _refresh_locked(self, now: float) -> None:
        if (
            self._state is CircuitState.OPEN
            and self._opened_at is not None
            and now - self._opened_at >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_probe = False


Transport = Callable[[Any], Any | Awaitable[Any]]
AuditSink = Callable[[AuditEvent], Any | Awaitable[Any]]


class ResilientMLClient:
    """Generic async facade for an ML scorer that fails closed to deterministic rules.

    This component performs no inference itself, imports no GPU/LLM runtime, and never
    stores a successful score. A caller must explicitly decide how to combine the returned
    score with rules; on fallback, ``result.score`` is always ``None``.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        timeout: float = 2.0,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        max_score_age: float | None = 300.0,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        audit_sink: AuditSink | None = None,
        default_mode: FallbackMode | str = FallbackMode.HYBRID_ML,
    ) -> None:
        if timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("timeout must be finite and positive")
        if max_retries < 0 or max_retries > 5:
            raise ValueError("max_retries must be between 0 and 5")
        if max_score_age is not None and (max_score_age < 0 or not math.isfinite(max_score_age)):
            raise ValueError("max_score_age must be None or finite and non-negative")
        self.transport = transport
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self.max_score_age = max_score_age
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic
        self.audit_sink = audit_sink
        self.default_mode = self._mode(default_mode)

    async def score(
        self,
        request: Any = None,
        *,
        mode: FallbackMode | str | None = None,
        as_of: date | datetime | str | None = None,
        max_score_age: float | None = None,
    ) -> MLScoreResult:
        selected_mode = self.default_mode if mode is None else self._mode(mode)
        if selected_mode is FallbackMode.RULES_ONLY:
            return await self._fallback(
                selected_mode,
                FallbackCause(
                    code="RULES_ONLY_EXPLICIT",
                    category=CauseCategory.CONFIGURATION,
                    message="RULES_ONLY was explicitly selected; the ML dependency was not called.",
                    details={"fallback": "RULES_ONLY"},
                ),
                attempts=0,
                metadata={"request": self._safe_metadata(request)},
            )

        if not self.circuit_breaker.allow_request(self._monotonic()):
            return await self._fallback(
                selected_mode,
                FallbackCause(
                    code="ML_CIRCUIT_OPEN",
                    category=CauseCategory.CIRCUIT,
                    message="The in-memory ML circuit is open; rules-only fallback is active.",
                    retryable=True,
                    details={"circuit": self.circuit_breaker.snapshot()},
                ),
                attempts=0,
                metadata={"request": self._safe_metadata(request)},
            )

        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            try:
                raw = await self._call_with_timeout(request)
            except asyncio.TimeoutError:
                cause = FallbackCause(
                    code="ML_TIMEOUT",
                    category=CauseCategory.TIMEOUT,
                    message="The ML dependency exceeded its configured timeout.",
                    retryable=True,
                    attempts=attempts,
                )
                if attempts <= self.max_retries:
                    continue
                return await self._failed(selected_mode, cause, attempts, request)
            except Exception as exc:  # noqa: BLE001 - dependency failures are normalized below
                status_code = self._status_code(exc)
                retryable = status_code is None or status_code == 429 or status_code >= 500
                cause = FallbackCause(
                    code=(
                        "ML_HTTP_5XX"
                        if status_code is not None and status_code >= 500
                        else "ML_UNAVAILABLE"
                    ),
                    category=(
                        CauseCategory.HTTP if status_code is not None else CauseCategory.NETWORK
                    ),
                    message="The ML dependency is unavailable.",
                    retryable=retryable,
                    status_code=status_code,
                    attempts=attempts,
                    details={"exception": type(exc).__name__},
                )
                if retryable and attempts <= self.max_retries:
                    continue
                return await self._failed(selected_mode, cause, attempts, request)

            status_code = self._status_code(raw)
            if status_code is not None and status_code >= 400:
                retryable = status_code == 429 or status_code >= 500
                cause = FallbackCause(
                    code="ML_HTTP_5XX" if status_code >= 500 else "ML_UNAVAILABLE",
                    category=CauseCategory.HTTP,
                    message="The ML dependency returned an unsuccessful response.",
                    retryable=retryable,
                    status_code=status_code,
                    attempts=attempts,
                )
                if retryable and attempts <= self.max_retries:
                    continue
                return await self._failed(selected_mode, cause, attempts, request)

            response = self._as_mapping(raw)
            value = self._extract_score(response, raw)
            if value is None:
                cause = FallbackCause(
                    code="ML_SCORE_ABSENT",
                    category=CauseCategory.SCORE,
                    message="The ML response did not contain a valid propensity score.",
                    attempts=attempts,
                )
                return await self._failed(selected_mode, cause, attempts, request)
            stale, freshness = self._is_stale(response, as_of, max_score_age)
            if stale:
                cause = FallbackCause(
                    code="ML_SCORE_STALE",
                    category=CauseCategory.SCORE,
                    message=(
                        "The ML response contains a score older than the configured "
                        "freshness window."
                    ),
                    attempts=attempts,
                    details=freshness,
                )
                return await self._failed(selected_mode, cause, attempts, request)
            self.circuit_breaker.record_success()
            event = AuditEvent(
                event_type="ML_SCORE_ACCEPTED",
                occurred_at=self._now().isoformat(),
                mode=selected_mode,
                circuit_state=self.circuit_breaker.state,
                cause=None,
                attempts=attempts,
                score_present=True,
                metadata={"freshness": freshness},
            )
            await self._emit(event)
            return MLScoreResult(
                score=value,
                mode=selected_mode,
                used_ml=True,
                cause=None,
                audit_event=event,
                attempts=attempts,
                circuit_state=self.circuit_breaker.state,
                response=response,
            )

        raise AssertionError("retry loop exhausted without a result")

    predict = score
    get_score = score

    async def _failed(
        self,
        mode: FallbackMode,
        cause: FallbackCause,
        attempts: int,
        request: Any,
    ) -> MLScoreResult:
        self.circuit_breaker.record_failure(self._monotonic())
        cause = FallbackCause(
            code=cause.code,
            category=cause.category,
            message=cause.message,
            retryable=cause.retryable,
            status_code=cause.status_code,
            attempts=attempts,
            details={**cause.details, "fallback": FallbackMode.RULES_ONLY.value},
        )
        return await self._fallback(
            FallbackMode.RULES_ONLY,
            cause,
            attempts=attempts,
            metadata={"request": self._safe_metadata(request)},
        )

    async def _fallback(
        self,
        _mode: FallbackMode,
        cause: FallbackCause,
        *,
        attempts: int,
        metadata: Mapping[str, Any],
    ) -> MLScoreResult:
        state = self.circuit_breaker.state
        event = AuditEvent(
            event_type="ML_FALLBACK_APPLIED",
            occurred_at=self._now().isoformat(),
            mode=FallbackMode.RULES_ONLY,
            circuit_state=state,
            cause=cause,
            attempts=attempts,
            score_present=False,
            metadata=dict(metadata),
        )
        await self._emit(event)
        return MLScoreResult(
            score=None,
            mode=FallbackMode.RULES_ONLY,
            used_ml=False,
            cause=cause,
            audit_event=event,
            attempts=attempts,
            circuit_state=state,
            response=None,
        )

    async def _call_with_timeout(self, request: Any) -> Any:
        async def invoke() -> Any:
            value = self.transport(request)
            if inspect.isawaitable(value):
                return await value
            return value

        return await asyncio.wait_for(invoke(), timeout=self.timeout)

    async def _emit(self, event: AuditEvent) -> None:
        if self.audit_sink is None:
            return
        try:
            result = self.audit_sink(event)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - audit must not disable deterministic fallback
            return

    def _now(self) -> datetime:
        current = self.clock()
        if current.tzinfo is None:
            return current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc)

    def _is_stale(
        self,
        response: Mapping[str, Any],
        as_of: date | datetime | str | None,
        max_score_age: float | None,
    ) -> tuple[bool, dict[str, Any]]:
        age_limit = self.max_score_age if max_score_age is None else max_score_age
        scored_at = self._first(response, "scoredAt", "scored_at", "generatedAt", "generated_at")
        response_as_of = self._first(
            response,
            "asOf",
            "as_of",
            "observationAsOf",
            "observation_as_of",
        )
        details: dict[str, Any] = {
            "scoredAt": scored_at,
            "asOf": response_as_of,
            "maxAgeSeconds": age_limit,
        }
        if as_of is not None and response_as_of is not None:
            expected = self._parse_date_or_datetime(as_of)
            actual = self._parse_date_or_datetime(response_as_of)
            if expected is not None and actual is not None and actual < expected:
                details.update({"expectedAsOf": str(as_of), "actualAsOf": str(response_as_of)})
                return True, details
        if age_limit is None or scored_at is None:
            return False, details
        parsed = self._parse_date_or_datetime(scored_at)
        if parsed is None:
            details["invalidScoredAt"] = True
            return True, details
        age = (self._now() - parsed).total_seconds()
        details["ageSeconds"] = age
        return age > age_limit, details

    @staticmethod
    def _extract_score(response: Mapping[str, Any], raw: Any) -> float | None:
        candidate: Any = None
        for key in ("propensity", "score", "propensityScore", "propensity_score"):
            if key in response:
                candidate = response[key]
                break
        if candidate is None:
            for key in ("propensity", "score", "propensity_score"):
                if hasattr(raw, key):
                    candidate = getattr(raw, key)
                    break
        if isinstance(candidate, bool):
            return None
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and 0.0 <= value <= 1.0 else None

    @staticmethod
    def _as_mapping(raw: Any) -> Mapping[str, Any]:
        if isinstance(raw, Mapping):
            return raw
        if hasattr(raw, "json") and callable(raw.json):
            try:
                value = raw.json()
                return value if isinstance(value, Mapping) else {}
            except (TypeError, ValueError):
                return {}
        return {}

    @staticmethod
    def _status_code(value: Any) -> int | None:
        raw = getattr(value, "status_code", None)
        if raw is None and isinstance(value, Mapping):
            raw = value.get("status_code", value.get("statusCode"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in mapping:
                return mapping[key]
        return None

    @staticmethod
    def _parse_date_or_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    parsed_date = date.fromisoformat(value)
                    return datetime(
                        parsed_date.year,
                        parsed_date.month,
                        parsed_date.day,
                        tzinfo=timezone.utc,
                    )
                except ValueError:
                    return None
        return None

    @staticmethod
    def _mode(value: FallbackMode | str) -> FallbackMode:
        try:
            return FallbackMode(value)
        except ValueError as exc:
            raise ValueError("mode must be HYBRID_ML or RULES_ONLY") from exc

    @staticmethod
    def _safe_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return {
                str(key): repr(item)
                for key, item in value.items()
                if str(key).lower() not in {"authorization", "token"}
            }
        return {"requestType": type(value).__name__}


__all__ = [
    "AuditEvent",
    "CauseCategory",
    "CircuitBreaker",
    "CircuitState",
    "FallbackCause",
    "FallbackMode",
    "MLClientResult",
    "MLScoreResult",
    "ResilienceAuditEvent",
    "ResilientMLClient",
    "StructuredCause",
]
