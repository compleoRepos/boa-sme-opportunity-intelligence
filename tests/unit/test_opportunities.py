from boa_oi.opportunities import OpportunityEngine
from boa_oi.technical.config import RuleSetConfig


def types(engine, context):
    return {item.opportunity_type for item in engine.evaluate(context)}


def test_br001_investment_financing(rule_set, valid_context_factory):
    ctx = valid_context_factory(
        facts={
            "inflow_growth_rate": 0.40,
            "supplier_payment_growth_rate": 0.30,
            "transaction_volume_growth_rate": 0.20,
            "no_recent_investment_financing": True,
            "persistence_score": 0.9,
        }
    )
    result = OpportunityEngine(rule_set).evaluate(ctx)
    assert len(result) == 1 and result[0].opportunity_type == "INVESTMENT_FINANCING"
    assert result[0].horizon == "1-3_MONTHS" and len(result[0].why) == 4
    assert result[0].recommended_products == (
        "INVESTMENT_FINANCING",
        "WORKING_CAPITAL_FACILITY",
    )


def test_br002_trade_finance(rule_set, valid_context_factory):
    facts = {
        "international_flow_growth_rate": 0.50,
        "international_frequency_growth_rate": 0.25,
        "international_frequency_confirmed": True,
        "trade_finance_gap": True,
    }
    result = OpportunityEngine(rule_set).evaluate(valid_context_factory(facts=facts))[0]
    assert result.opportunity_type == "TRADE_FINANCE" and result.horizon == "0-3_MONTHS"


def test_br003_cash_investment(rule_set, valid_context_factory):
    facts = {
        "average_balance": 1800000,
        "surplus_day_ratio": 0.85,
        "surplus_persistence_periods": 3,
        "credit_line_utilization": 0.10,
    }
    result = OpportunityEngine(rule_set).evaluate(valid_context_factory(facts=facts))[0]
    assert result.opportunity_type == "CASH_INVESTMENT" and result.horizon == "0-1_MONTH"


def test_br004_financial_stress_is_relational(rule_set, valid_context_factory):
    facts = {
        "inflow_growth_rate": -0.35,
        "balance_growth_rate": -0.25,
        "credit_utilization_change": 0.40,
    }
    result = OpportunityEngine(rule_set).evaluate(valid_context_factory(facts=facts))[0]
    assert result.opportunity_type == "FINANCIAL_STRESS_SIGNAL"
    serialized = result.model_dump_json().lower()
    assert (
        "risk_score" not in serialized
        and "credit_score" not in serialized
        and "default_probability" not in serialized
    )


def test_financial_stress_accepts_either_decline_not_neither(rule_set, valid_context_factory):
    engine = OpportunityEngine(rule_set)
    assert "FINANCIAL_STRESS_SIGNAL" in types(
        engine,
        valid_context_factory(
            facts={
                "inflow_growth_rate": -0.30,
                "balance_growth_rate": 0,
                "credit_utilization_change": 0.30,
            }
        ),
    )
    assert "FINANCIAL_STRESS_SIGNAL" not in types(
        engine,
        valid_context_factory(
            facts={
                "inflow_growth_rate": -0.10,
                "balance_growth_rate": -0.10,
                "credit_utilization_change": 0.30,
            }
        ),
    )


def test_strict_boundaries_do_not_trigger(rule_set, valid_context_factory):
    engine = OpportunityEngine(rule_set)
    growth = {
        "inflow_growth_rate": 0.25,
        "supplier_payment_growth_rate": 0.20,
        "transaction_volume_growth_rate": 0.15,
        "no_recent_investment_financing": True,
    }
    trade = {
        "international_flow_growth_rate": 0.30,
        "international_frequency_growth_rate": 0.10,
        "international_frequency_confirmed": True,
        "trade_finance_gap": True,
    }
    stress = {
        "inflow_growth_rate": -0.25,
        "balance_growth_rate": -0.20,
        "credit_utilization_change": 0.20,
    }
    assert not types(engine, valid_context_factory(facts=growth))
    assert not types(engine, valid_context_factory(facts=trade))
    assert not types(engine, valid_context_factory(facts=stress))


def test_product_exclusions_and_missing_conditions(rule_set, valid_context_factory):
    engine = OpportunityEngine(rule_set)
    growth = {
        "inflow_growth_rate": 0.40,
        "supplier_payment_growth_rate": 0.30,
        "transaction_volume_growth_rate": 0.20,
        "no_recent_investment_financing": False,
    }
    trade = {
        "international_flow_growth_rate": 0.50,
        "international_frequency_growth_rate": 0.20,
        "international_frequency_confirmed": True,
        "trade_finance_gap": False,
    }
    assert not types(engine, valid_context_factory(facts=growth))
    assert not types(engine, valid_context_factory(facts=trade))


def test_false_positive_guards(rule_set, valid_context_factory):
    engine = OpportunityEngine(rule_set)
    facts = {
        "inflow_growth_rate": 0.60,
        "supplier_payment_growth_rate": 0.50,
        "transaction_volume_growth_rate": 0.40,
        "no_recent_investment_financing": True,
    }
    for overrides in (
        {"seasonality_adjusted": False},
        {"false_positive_flags": ("ONE_OFF_TRANSACTION",)},
        {"data_quality": "INSUFFICIENT_HISTORY"},
        {"data_coverage": 0.5},
    ):
        assert not engine.evaluate(valid_context_factory(facts=facts, **overrides))


def test_international_one_off_and_cash_one_period_do_not_trigger(rule_set, valid_context_factory):
    engine = OpportunityEngine(rule_set)
    international = {
        "international_flow_growth_rate": 2.0,
        "international_frequency_growth_rate": 0,
        "international_frequency_confirmed": False,
        "trade_finance_gap": True,
    }
    cash = {
        "average_balance": 2000000,
        "surplus_day_ratio": 0.9,
        "surplus_persistence_periods": 1,
        "credit_line_utilization": 0.1,
    }
    assert "TRADE_FINANCE" not in types(engine, valid_context_factory(facts=international))
    assert "CASH_INVESTMENT" not in types(engine, valid_context_factory(facts=cash))


def test_same_input_same_output_and_two_rules_can_coexist(rule_set, valid_context_factory):
    facts = {
        "inflow_growth_rate": 0.40,
        "supplier_payment_growth_rate": 0.30,
        "transaction_volume_growth_rate": 0.20,
        "no_recent_investment_financing": True,
        "average_balance": 2000000,
        "surplus_day_ratio": 0.9,
        "surplus_persistence_periods": 3,
        "credit_line_utilization": 0.1,
    }
    engine = OpportunityEngine(rule_set)
    ctx = valid_context_factory(facts=facts)
    first = engine.evaluate(ctx)
    second = engine.evaluate(ctx)
    assert first == second and types(engine, ctx) == {
        "INVESTMENT_FINANCING",
        "CASH_INVESTMENT",
    }


def test_configured_threshold_change_changes_decision(rule_set, valid_context_factory):
    raw = rule_set.model_dump(mode="python")
    raw["rule_set_version"] = "changed"
    raw["opportunity_rules"]["INVESTMENT_FINANCING"]["all_conditions"][0]["value"] = 0.50
    changed = RuleSetConfig.model_validate(raw)
    facts = {
        "inflow_growth_rate": 0.40,
        "supplier_payment_growth_rate": 0.30,
        "transaction_volume_growth_rate": 0.20,
        "no_recent_investment_financing": True,
    }
    assert OpportunityEngine(rule_set).evaluate(valid_context_factory(facts=facts))
    assert not OpportunityEngine(changed).evaluate(valid_context_factory(facts=facts))
