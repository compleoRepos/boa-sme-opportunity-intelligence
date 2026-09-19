import pytest
from boa_oi.operations import (
    DriftDomain,
    DriftMonitor,
    DriftThresholds,
    LowerBoundThresholds,
    ObservabilityEvent,
    OperationalMetrics,
    OperationalMonitor,
    OperationalThresholds,
    ReadinessAggregator,
    ReadinessStatus,
    Severity,
    Thresholds,
    production_readiness,
    rules_only_rate,
)


def test_configurable_drift_thresholds_classify_warning_and_critical():
    thresholds = DriftThresholds(0.1, 0.2, method="PSI", reference_version="features-v1")
    monitor = DriftMonitor({DriftDomain.FEATURE: thresholds})
    warning = monitor.observe("FEATURE", "psi", 0.15, segment="SMALL", sample_size=100)
    critical = monitor.observe("FEATURE", "psi", 0.25)
    assert warning.severity is Severity.WARNING
    assert critical.severity is Severity.CRITICAL and critical.is_blocking
    assert monitor.latest("FEATURE") == (warning, critical)
    assert warning.to_dict()["referenceVersion"] == "features-v1"


def test_rules_only_rate_is_safe_and_explicit():
    assert rules_only_rate(2, 10) == 0.2
    assert rules_only_rate(0, 0) == 0.0
    with pytest.raises(ValueError):
        rules_only_rate(3, 2)


def test_operational_monitor_tracks_latency_errors_volume_and_rules_only_rate():
    thresholds = OperationalThresholds(
        latency_ms=Thresholds(100, 200),
        error_rate=Thresholds(0.01, 0.05),
        volume=LowerBoundThresholds(10, 5),
        rules_only_rate=Thresholds(0.2, 0.5),
    )
    observation = OperationalMonitor(thresholds).observe(
        OperationalMetrics(latency_ms=250, errors=1, requests=10, volume=4, rules_only_count=6)
    )
    assert observation.severity is Severity.CRITICAL
    assert observation.severities["latency"] is Severity.CRITICAL
    assert observation.severities["volume"] is Severity.CRITICAL
    assert observation.severities["rulesOnlyRate"] is Severity.CRITICAL
    assert observation.to_dict()["errorRate"] == 0.1


def test_history_is_bounded_and_audit_payload_is_structured():
    from boa_oi.operations import AuditEvent, MonitoringHistory, audit_event

    history = MonitoringHistory(max_entries=1)
    history.append(
        audit_event("DRIFT", "feature:psi", Severity.WARNING, {"value": 0.15}, trace_id="t-1")
    )
    history.append(
        audit_event("DRIFT", "feature:psi", Severity.CRITICAL, {"value": 0.25}, trace_id="t-2")
    )
    assert len(history.all()) == 1
    event = history.all()[0]
    assert isinstance(event, AuditEvent)
    assert event.to_dict()["traceId"] == "t-2"


def test_end_to_end_observability_contract_has_required_fields_and_camel_case():
    event = ObservabilityEvent(
        trace_id="trace-1",
        service="scoring",
        endpoint="/v1/opportunities/score",
        status=200,
        latency=42.5,
        model_version="model-v1",
        scoring_policy_version="policy-v3",
        fallback_mode="RULES_ONLY",
    )
    payload = event.to_dict()
    required = {
        "traceId",
        "service",
        "endpoint",
        "status",
        "latency",
        "modelVersion",
        "scoringPolicyVersion",
        "fallbackMode",
    }
    assert required <= payload.keys()
    assert ObservabilityEvent.from_mapping(payload) == event


def test_readiness_guardrail_never_reports_production_when_real_prerequisites_are_missing():
    report = production_readiness(components={"contracts": True, "structured_audit": True})
    assert report.status is ReadinessStatus.NOT_READY
    assert "historical_data" in report.to_dict()["blockingComponents"]
    assert len(report.components) == len(ReadinessAggregator().required_components)


def test_readiness_can_report_production_only_when_every_required_component_passes():
    aggregator = ReadinessAggregator()
    report = aggregator.evaluate(dict.fromkeys(aggregator.required_components, True))
    assert report.status is ReadinessStatus.READY_FOR_PRODUCTION
    assert not report.blocking_components


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError):
        Thresholds(2, 1)
    with pytest.raises(ValueError):
        ObservabilityEvent("t", "s", "/x", 200, -1)
