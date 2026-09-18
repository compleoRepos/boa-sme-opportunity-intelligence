import math

import pytest
from boa_oi.confidence import ConfidenceScoreCalculator
from boa_oi.priority import PriorityScoreCalculator


def test_confidence_components_bounds_levels_and_missing():
    calc = ConfidenceScoreCalculator({"a": 60, "b": 40})
    high = calc.calculate({"a": 2, "b": 1})
    medium = calc.calculate({"a": 1, "b": 0})
    low = calc.calculate({"a": None, "b": 0.5})
    assert (high.score, high.level) == (1, "HIGH")
    assert medium.level == "MEDIUM" and low.level == "LOW"
    assert low.components[0].normalized_value == 0 and not math.isnan(low.score)


def test_confidence_cap_and_invalid_values():
    calc = ConfidenceScoreCalculator({"a": 1})
    assert calc.calculate({"a": 1}, score_cap=0.65).score == 0.65
    with pytest.raises(ValueError):
        calc.calculate({"a": float("nan")})
    with pytest.raises(ValueError):
        ConfidenceScoreCalculator({"a": 0})


def test_priority_formula_levels_and_neutral_relationship(rule_set):
    cfg = rule_set.priority
    calc = PriorityScoreCalculator(cfg.weights, p1=cfg.p1, p2=cfg.p2, p3=cfg.p3)
    result = calc.calculate(
        {
            "confidence": 1,
            "signal_strength": 1,
            "urgency": 1,
            "recency": 1,
            "relationship_context": None,
            "product_gap": 1,
        }
    )
    assert result.score == 95 and result.level == "P1"
    assert (
        next(x for x in result.components if x.name == "relationship_context").normalized_value
        == 0.5
    )


def test_low_confidence_caps_priority_and_ties_are_stable(rule_set):
    cfg = rule_set.priority
    calc = PriorityScoreCalculator(cfg.weights, p1=cfg.p1, p2=cfg.p2, p3=cfg.p3)
    factors = dict.fromkeys(cfg.weights, 1)
    first = calc.calculate(factors, confidence_level="LOW")
    second = calc.calculate(factors, confidence_level="LOW")
    assert first == second and first.level == "P3"


def test_priority_rejects_invalid_weights_and_nan():
    with pytest.raises(ValueError):
        PriorityScoreCalculator({"a": 0.9})
    calc = PriorityScoreCalculator({"a": 1})
    with pytest.raises(ValueError):
        calc.calculate({"a": float("inf")})
