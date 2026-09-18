from __future__ import annotations

from datetime import date

import pytest
from boa_oi.opportunity_api import rule_engine_candidates, rule_engine_metrics
from boa_oi.rules import RuleEvaluator, canonical_operator
from boa_oi.rules.simulation import metric_payload


def definition(conditions, logic="AND"):
    return {
        "name": "Configured test rule",
        "description": "No business threshold is hardcoded in the evaluator.",
        "conditions": conditions,
        "logic": logic,
        "recommendation": {
            "opportunityType": "TEST_OPPORTUNITY",
            "products": ["PRODUCT_CODE"],
            "horizon": "1_3_MONTHS",
        },
        "confidence": {"baseScore": 50, "weights": {"growth": 25}},
    }


@pytest.mark.parametrize(
    ("operator", "value", "actual", "matched"),
    [
        (">", 2, 3, True),
        (">=", 3, 3, True),
        ("<", 4, 3, True),
        ("<=", 3, 3, True),
        ("=", "SME", "SME", True),
        ("!=", "CORPORATE", "SME", True),
        ("BETWEEN", [2, 4], 3, True),
        ("IN", ["SME", "MICRO"], "SME", True),
        ("NOT_IN", ["CORPORATE"], "SME", True),
    ],
)
def test_comparison_operators(operator, value, actual, matched):
    result = RuleEvaluator().evaluate(
        definition([{"metric": "metric", "operator": operator, "value": value}]),
        {"metric": actual},
    )
    assert result.matched is matched
    assert result.evidence[0]["result"] is matched


def test_change_and_persistence_operators():
    conditions = [
        {
            "metric": "growth",
            "operator": "INCREASE_BY",
            "value": 25,
            "unit": "PERCENT",
        },
        {
            "metric": "decline",
            "operator": "DECREASE_BY",
            "value": 20,
            "unit": "PERCENT",
        },
        {
            "metric": "persistent",
            "operator": "PERSISTENT_FOR",
            "value": 3,
        },
    ]
    metrics = {
        "growth": {"currentValue": 125, "previousPeriodValue": 100},
        "decline": {"currentValue": 80, "previousPeriodValue": 100},
        "persistent": {"history": [False, True, True, True]},
    }
    result = RuleEvaluator().evaluate(definition(conditions), metrics)
    assert result.matched
    assert all(item["result"] for item in result.evidence)


def test_nested_and_or_not_and_missing_metrics_are_explainable():
    nested = [
        {
            "logic": "OR",
            "conditions": [
                {"metric": "a", "operator": ">", "value": 10},
                {"metric": "missing", "operator": "=", "value": True},
            ],
        },
        {
            "logic": "NOT",
            "conditions": [{"metric": "segment", "operator": "=", "value": "CORPORATE"}],
        },
    ]
    result = RuleEvaluator().evaluate(definition(nested), {"a": 11, "segment": "SME"})
    assert result.matched
    missing = next(item for item in result.evidence if item["metric"] == "missing")
    assert missing["actual"] is None
    assert "unavailableReason" in missing
    assert result.explanation["logic"] == "AND"


def test_percent_thresholds_are_configuration_values_and_confidence_is_bounded():
    rule = definition(
        [{"metric": "growth", "operator": "GREATER_THAN", "value": 25, "unit": "PERCENT"}]
    )
    rule["confidence"] = {"baseScore": 90, "weights": {"growth": 30}}
    result = RuleEvaluator().evaluate(rule, {"growth": 0.36})
    assert result.matched
    assert result.evidence[0]["threshold"] == 0.25
    assert result.confidence == 1.0
    assert canonical_operator("GREATER_THAN") == ">"


def test_analytics_growth_aliases_and_published_rule_trace_are_preserved():
    values = {
        "inflow_amount": {
            "currentValue": 1_420_000,
            "previousPeriodValue": 1_000_000,
            "growthRate": 0.42,
            "change": 420_000,
        }
    }
    simulation_metrics = metric_payload(values)
    production_metrics = rule_engine_metrics(
        [{"metric": "inflow_amount", "period": "90D", **values["inflow_amount"]}]
    )
    assert simulation_metrics["INFLOW_GROWTH"] == 0.42
    assert production_metrics["INFLOW_GROWTH:90D"] == 0.42

    candidates = rule_engine_candidates(
        "SME-00001",
        date(2026, 9, 18),
        {
            "matched": True,
            "ruleId": "RULE-PUBLISHED",
            "ruleVersion": 3,
            "engineVersion": "rule-engine-0.1.0",
            "opportunityType": "INVESTMENT_FINANCING",
            "productCodes": ["CASH_MANAGEMENT"],
            "horizon": "1-3_MONTHS",
            "confidence": 0.9,
            "evidence": [
                {
                    "metric": "INFLOW_GROWTH",
                    "operator": ">",
                    "actual": 0.42,
                    "threshold": 0.25,
                    "result": True,
                }
            ],
        },
    )
    assert len(candidates) == 1
    assert candidates[0].rule_version == "RULE-PUBLISHED:v3"
    assert candidates[0].engine_version == "rule-engine-0.1.0"
    assert candidates[0].evidence[0].observed == 0.42
