from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from boa_oi.resilience import (
    CircuitBreaker,
    CircuitState,
    FallbackMode,
    ResilientMLClient,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def test_ml_ok_returns_score_and_accept_audit_event():
    events = []

    async def transport(_request):
        return {
            "propensity": 0.73,
            "modelVersion": "model-v1",
            "asOf": "2026-09-19",
            "scoredAt": NOW.isoformat(),
        }

    client = ResilientMLClient(
        transport,
        timeout=0.1,
        max_retries=2,
        clock=lambda: NOW,
        audit_sink=events.append,
    )

    result = asyncio.run(client.score({"customerId": "SME-1"}, as_of="2026-09-19"))

    assert result.score == pytest.approx(0.73)
    assert result.used_ml is False
    assert result.mode is FallbackMode.POC_SHADOW
    assert result.cause is None
    assert result.attempts == 1
    assert result.audit_event.event_type == "ML_SHADOW_SCORE_OBSERVED"
    assert events == [result.audit_event]
    assert client.circuit_breaker.state is CircuitState.CLOSED


def test_timeout_retries_then_falls_back_without_reusing_score():
    calls = 0
    events = []

    async def transport(_request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"propensity": 0.99}

    client = ResilientMLClient(
        transport,
        timeout=0.001,
        max_retries=2,
        clock=lambda: NOW,
        audit_sink=events.append,
    )

    result = asyncio.run(client.score({"customerId": "SME-1"}))

    assert calls == 3
    assert result.score is None
    assert result.used_ml is False
    assert result.mode is FallbackMode.RULES_ONLY
    assert result.cause is not None
    assert result.cause.code == "ML_TIMEOUT"
    assert result.cause.attempts == 3
    assert result.audit_event.event_type == "ML_FALLBACK_APPLIED"
    assert result.audit_event.score_present is False
    assert events == [result.audit_event]


def test_http_500_is_retried_and_falls_back_with_structured_cause():
    calls = 0

    async def transport(_request):
        nonlocal calls
        calls += 1
        return {"status_code": 500, "message": "down"}

    client = ResilientMLClient(transport, max_retries=1, clock=lambda: NOW)
    result = asyncio.run(client.score())

    assert calls == 2
    assert result.score is None
    assert result.cause is not None
    assert result.cause.code == "ML_HTTP_5XX"
    assert result.cause.category == "HTTP"
    assert result.cause.status_code == 500
    assert result.cause.retryable is True


def test_unavailable_exception_is_bounded_and_falls_back():
    calls = 0

    async def transport(_request):
        nonlocal calls
        calls += 1
        raise ConnectionError("connection refused")

    client = ResilientMLClient(transport, max_retries=1, clock=lambda: NOW)
    result = asyncio.run(client.score())

    assert calls == 2
    assert result.score is None
    assert result.cause is not None
    assert result.cause.code == "ML_UNAVAILABLE"
    assert result.cause.category == "NETWORK"
    assert result.cause.details["exception"] == "ConnectionError"


def test_missing_score_is_not_accepted_or_cached():
    async def transport(_request):
        return {"modelVersion": "model-v1", "asOf": "2026-09-19"}

    client = ResilientMLClient(
        transport,
        clock=lambda: NOW,
        max_score_age=None,
    )
    result = asyncio.run(client.score())

    assert result.score is None
    assert result.cause is not None
    assert result.cause.code == "ML_SCORE_ABSENT"
    assert result.response is None


def test_obsolete_score_falls_back_and_does_not_reuse_previous_score():
    responses = iter(
        [
            {"propensity": 0.81, "scoredAt": NOW.isoformat()},
            {"propensity": 0.99, "scoredAt": (NOW - timedelta(seconds=301)).isoformat()},
        ]
    )

    async def transport(_request):
        return next(responses)

    client = ResilientMLClient(transport, max_score_age=300, clock=lambda: NOW)
    fresh = asyncio.run(client.score())
    stale = asyncio.run(client.score())

    assert fresh.score == pytest.approx(0.81)
    assert stale.score is None
    assert stale.cause is not None
    assert stale.cause.code == "ML_SCORE_STALE"
    assert stale.response is None


def test_explicit_rules_only_does_not_call_ml_and_emits_audit():
    calls = 0
    events = []

    async def transport(_request):
        nonlocal calls
        calls += 1
        return {"propensity": 0.5}

    client = ResilientMLClient(transport, audit_sink=events.append, clock=lambda: NOW)
    result = asyncio.run(client.score(mode="RULES_ONLY"))

    assert calls == 0
    assert result.score is None
    assert result.mode is FallbackMode.RULES_ONLY
    assert result.cause is not None
    assert result.cause.code == "RULES_ONLY_EXPLICIT"
    assert events[0].event_type == "ML_FALLBACK_APPLIED"


def test_circuit_opens_after_failures_and_recovers_with_half_open_probe():
    clock = [100.0]
    calls = 0
    should_fail = True

    async def transport(_request):
        nonlocal calls
        calls += 1
        if should_fail:
            raise ConnectionError("down")
        return {"propensity": 0.64, "scoredAt": NOW.isoformat()}

    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=10,
        clock=lambda: clock[0],
    )
    client = ResilientMLClient(
        transport,
        max_retries=0,
        circuit_breaker=breaker,
        monotonic=lambda: clock[0],
        clock=lambda: NOW,
    )

    first = asyncio.run(client.score())
    second = asyncio.run(client.score())
    blocked = asyncio.run(client.score())
    assert first.cause is not None and first.cause.code == "ML_UNAVAILABLE"
    assert second.cause is not None and second.cause.code == "ML_UNAVAILABLE"
    assert breaker.state is CircuitState.OPEN
    assert blocked.cause is not None and blocked.cause.code == "ML_CIRCUIT_OPEN"
    assert blocked.mode is FallbackMode.RULES_ONLY
    assert blocked.audit_event.mode is FallbackMode.RULES_ONLY
    assert calls == 2

    clock[0] = 111.0
    should_fail = False
    recovered = asyncio.run(client.score())

    assert recovered.score == pytest.approx(0.64)
    assert recovered.used_ml is False
    assert recovered.mode is FallbackMode.POC_SHADOW
    assert recovered.circuit_state is CircuitState.CLOSED
    assert calls == 3
