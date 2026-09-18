from datetime import date, timedelta
from decimal import Decimal

import pytest
from boa_oi.analytics import AnalyticsEngine, BalanceFact, TransactionFact, growth_rate

AS_OF = date(2026, 9, 30)


def tx(ref, day, direction, amount, **kw):
    return TransactionFact(
        ref,
        "SME-1",
        "ACC-1",
        day,
        direction,
        Decimal(str(amount)),
        kw.pop("category", "CUSTOMER_RECEIPT"),
        **kw,
    )


def balances(days=90, value=1000, used=100, limit=1000):
    return [
        BalanceFact(
            "ACC-1",
            AS_OF - timedelta(days=i),
            Decimal(str(value)),
            Decimal(str(limit)),
            Decimal(str(used)),
        )
        for i in range(days)
    ]


@pytest.mark.parametrize("window", [7, 30, 90, 180, 365])
def test_supported_windows(window):
    result = AnalyticsEngine().calculate("SME-1", [], balances(window), AS_OF, window)
    assert result.window_days == window
    assert result.metrics["average_balance"].sample_size == window


def test_inflows_outflows_supplier_international_and_count_exclusions():
    rows = [
        tx("1", AS_OF, "CREDIT", 10000),
        tx("2", AS_OF, "DEBIT", 3000, category="SUPPLIER_PAYMENT"),
        tx("3", AS_OF, "CREDIT", 5000, is_international=True),
        tx("4", AS_OF, "CREDIT", 9000, status="REVERSED"),
        tx("5", AS_OF, "CREDIT", 8000, is_internal_transfer=True),
        tx("6", AS_OF - timedelta(days=100), "CREDIT", 7000),
    ]
    result = AnalyticsEngine().calculate("SME-1", rows, balances(), AS_OF, 90)
    assert result.metrics["inflow_amount"].current_value == 15000
    assert result.metrics["outflow_amount"].current_value == 3000
    assert result.metrics["supplier_payment_amount"].current_value == 3000
    assert result.metrics["international_flow_amount"].current_value == 5000
    assert result.metrics["transaction_count"].current_value == 3


def test_previous_period_growth_and_sign_preserved():
    rows = [
        tx("current", AS_OF, "CREDIT", 14000),
        tx("previous", AS_OF - timedelta(days=100), "CREDIT", 10000),
    ]
    metric = (
        AnalyticsEngine().calculate("SME-1", rows, balances(), AS_OF, 90).metrics["inflow_amount"]
    )
    assert metric.growth_rate == Decimal("0.4")
    reverse = growth_rate(Decimal(75), Decimal(100), Decimal(1))[0]
    assert reverse == Decimal("-0.25")


def test_low_baseline_is_not_artificial_growth():
    rate, quality = growth_rate(Decimal(100), Decimal(0), Decimal(1000))
    assert rate is None and quality == "BASELINE_LOW"


def test_balance_statistics_utilization_and_coverage():
    rows = [
        BalanceFact(
            "ACC-1",
            AS_OF - timedelta(days=i),
            Decimal(1000 + i),
            Decimal(1000),
            Decimal(200),
        )
        for i in range(90)
    ]
    metrics = AnalyticsEngine().calculate("SME-1", [], rows, AS_OF, 90).metrics
    assert metrics["minimum_balance"].current_value == 1000
    assert metrics["maximum_balance"].current_value == 1089
    assert metrics["credit_line_utilization"].current_value == Decimal("0.2")
    assert metrics["average_balance"].data_coverage == 1


def test_partial_coverage_and_seasonality_guard():
    metric = (
        AnalyticsEngine()
        .calculate(
            "SME-1",
            [tx("1", AS_OF, "CREDIT", 2000)],
            balances(10),
            AS_OF,
            90,
            historical_values={"inflow_amount": [Decimal(3000), Decimal(3000)]},
        )
        .metrics["inflow_amount"]
    )
    assert metric.data_coverage < Decimal("0.83")
    assert metric.seasonality_adjusted is False


def test_wrong_customer_and_unsupported_window_rejected():
    engine = AnalyticsEngine()
    with pytest.raises(ValueError):
        engine.calculate("OTHER", [tx("1", AS_OF, "CREDIT", 1000)], balances(), AS_OF, 90)
    with pytest.raises(ValueError):
        engine.calculate("SME-1", [], [], AS_OF, 91)
