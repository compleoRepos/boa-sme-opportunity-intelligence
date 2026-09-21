from __future__ import annotations

from datetime import date

import pytest
from boa_oi.models.entities import OpportunityRule
from boa_oi.opportunity_api import (
    configured_rules,
    hydrate_recommended_products,
    rerank_with_propensity,
    rule_engine_candidates,
    rule_engine_metrics,
)
from boa_oi.platform import Problem
from boa_oi.rules import RuleEvaluator, canonical_operator
from boa_oi.rules.simulation import metric_payload
from boa_oi.technical.ids import deterministic_uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def definition(conditions, logic="AND"):
    return {
        "name": "Configured test rule",
        "description": "No business threshold is hardcoded in the evaluator.",
        "conditions": conditions,
        "logic": logic,
        "recommendation": {
            "opportunityType": "TEST_OPPORTUNITY",
            "products": ["BOA_CREDIT_MLTD_DIRECT"],
            "horizon": "1_3_MONTHS",
        },
        "confidence": {"baseScore": 50, "weights": {"growth": 25}},
    }


def test_configured_rules_ignore_rule_studio_adapter_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'opportunity'")
        OpportunityRule.__table__.create(connection)
        with Session(connection) as session:
            session.add(
                OpportunityRule(
                    id=deterministic_uuid("rule-studio-adapter-test"),
                    opportunity_type="RULE_STUDIO_TEST",
                    version="1",
                    configuration_json={"source": "rule-studio", "ruleId": "RULE-TEST"},
                    active=True,
                    created_by="unit-test",
                )
            )
            session.commit()
            config = configured_rules(session)

    assert "RULE_STUDIO_TEST" not in config.opportunity_rules


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
            "productCodes": ["BOA_CREDIT_MLTD_DIRECT"],
            "horizon": "1-3_MONTHS",
            "lifecycle": {
                "validityDays": 45,
                "dismissedCooldownDays": 60,
                "convertedCooldownDays": 200,
                "deferredCooldownDays": 20,
                "expiredCooldownDays": 5,
            },
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
    assert candidates[0].lifecycle_policy == {
        "validity_days": 45,
        "dismissed_cooldown_days": 60,
        "converted_cooldown_days": 200,
        "deferred_cooldown_days": 20,
        "expired_cooldown_days": 5,
    }


def test_published_rule_with_unknown_catalog_product_fails_closed():
    with pytest.raises(Problem) as exc_info:
        rule_engine_candidates(
            "SME-00001",
            date(2026, 9, 18),
            {
                "matched": True,
                "ruleId": "RULE-LEGACY",
                "ruleVersion": 1,
                "opportunityType": "INVESTMENT_FINANCING",
                "productCodes": ["INVESTMENT_FINANCING"],
                "confidence": 0.9,
                "evidence": [],
            },
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "UNKNOWN_RULE_PRODUCT_CODES"


def test_shadow_sales_propensity_never_changes_rules_priority():
    candidate = rule_engine_candidates(
        "SME-00001",
        date(2026, 9, 18),
        {
            "matched": True,
            "ruleId": "RULE-PUBLISHED",
            "ruleVersion": 3,
            "engineVersion": "rule-engine-0.1.0",
            "opportunityType": "INVESTMENT_FINANCING",
            "confidence": 0.7,
            "evidence": [],
        },
    )[0]

    def score(value: float):
        return {
            "propensity": value,
            "modelVersion": "sales-propensity-logit-poc-v1",
            "featureVersion": "sales-features-v2",
            "trainingDatasetVersion": "synthetic-demo-20260918-v1",
            "deploymentMode": "POC_SHADOW",
            "traceId": f"trace-{value}",
        }

    low = rerank_with_propensity(candidate, score(0.1), rules_weight=1.0, ml_weight=0.0)
    high = rerank_with_propensity(candidate, score(0.9), rules_weight=1.0, ml_weight=0.0)
    assert high.priority_score == low.priority_score
    assert high.priority_level == low.priority_level
    assert high.engine_version.endswith("+rules-only")
    assert low.engine_version.endswith("+rules-only")

    non_shadow = score(0.9)
    non_shadow["deploymentMode"] = "POC_ASSISTIVE"
    with pytest.raises(Problem) as exc_info:
        rerank_with_propensity(candidate, non_shadow, rules_weight=0.65, ml_weight=0.35)
    assert exc_info.value.code == "ML_SHADOW_POLICY_REQUIRED"


def test_known_but_inactive_rule_product_fails_closed_before_persistence():
    with pytest.raises(Problem) as exc_info:
        hydrate_recommended_products(
            ("BOA_CREDIT_MLTD_DIRECT",),
            {},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "UNAVAILABLE_RULE_PRODUCT_CODES"
