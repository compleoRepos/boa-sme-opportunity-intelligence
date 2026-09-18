from datetime import date

import pytest
from boa_oi.signals import MetricObservation, SignalDetector

AS_OF = date(2026, 9, 30)


def observation(metric="inflow_amount", value=0.30, **kw):
    defaults = {
        "metric": metric,
        "current_value": 1000,
        "growth_rate": value,
        "change": value,
        "historical_baseline": 700,
        "sample_size": 10,
        "data_coverage": 1,
        "confirmation_count": 2,
    }
    defaults.update(kw)
    return MetricObservation(**defaults)


def test_all_configured_signal_types_have_evaluators(rule_set):
    detector = SignalDetector(rule_set.signal_rules)
    observations = {
        "inflow_amount": observation(value=0.40),
        "outflow_amount": observation("outflow_amount", 0.30),
        "supplier_payment_amount": observation("supplier_payment_amount", 0.30),
        "international_flow_amount": observation("international_flow_amount", 0.50),
        "average_balance": observation(
            "average_balance", -0.30, current_value=1500000, sample_size=90
        ),
        "credit_line_utilization": observation(
            "credit_line_utilization", 0.30, current_value=0.6, sample_size=90
        ),
        "transaction_count": observation("transaction_count", 0.25),
    }
    types = {item.signal_type for item in detector.detect("SME-1", observations, AS_OF)}
    assert types == set(rule_set.signal_rules)


def test_signal_is_deterministic_explainable_and_confirmed(rule_set):
    detector = SignalDetector({"INFLOW_GROWTH": rule_set.signal_rules["INFLOW_GROWTH"]})
    first = detector.detect("SME-1", {"inflow_amount": observation(value=0.40)}, AS_OF)[0]
    second = detector.detect("SME-1", {"inflow_amount": observation(value=0.40)}, AS_OF)[0]
    assert first == second and first.status == "CONFIRMED" and len(first.evidence) == 3


@pytest.mark.parametrize("value", [0.24, 0.25])
def test_strict_threshold_not_reached_or_equal(rule_set, value):
    detector = SignalDetector({"INFLOW_GROWTH": rule_set.signal_rules["INFLOW_GROWTH"]})
    assert detector.detect("SME-1", {"inflow_amount": observation(value=value)}, AS_OF) == ()


def test_above_threshold_detected(rule_set):
    detector = SignalDetector({"INFLOW_GROWTH": rule_set.signal_rules["INFLOW_GROWTH"]})
    assert detector.detect("SME-1", {"inflow_amount": observation(value=0.251)}, AS_OF)


def test_missing_bad_short_and_seasonal_data_block_signal(rule_set):
    detector = SignalDetector({"INFLOW_GROWTH": rule_set.signal_rules["INFLOW_GROWTH"]})
    assert not detector.detect("SME-1", {}, AS_OF)
    assert not detector.detect(
        "SME-1",
        {"inflow_amount": observation(value=0.4, quality_status="DATA_INVALID")},
        AS_OF,
    )
    assert not detector.detect(
        "SME-1", {"inflow_amount": observation(value=0.4, sample_size=1)}, AS_OF
    )
    assert not detector.detect(
        "SME-1",
        {"inflow_amount": observation(value=0.4, seasonality_adjusted=False)},
        AS_OF,
    )


def test_unconfirmed_marginal_signal_remains_observed(rule_set):
    detector = SignalDetector({"INFLOW_GROWTH": rule_set.signal_rules["INFLOW_GROWTH"]})
    signal = detector.detect(
        "SME-1", {"inflow_amount": observation(value=0.27, confirmation_count=0)}, AS_OF
    )[0]
    assert signal.status == "OBSERVED" and signal.severity == "LOW"
