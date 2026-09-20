from datetime import date
from decimal import Decimal

import pytest
from boa_oi.adapters import (
    CanonicalAccount,
    CanonicalCustomer,
    CanonicalTransaction,
    InMemoryCoreBankingAdapter,
    InMemoryPaymentAdapter,
    InMemoryProductAdapter,
)
from boa_oi.audit import (
    DecisionAuditBuilder,
    canonical_hash,
    ensure_relational_language,
)
from boa_oi.technical.config import RuleSetConfig
from boa_oi.technical.ids import deterministic_uuid
from pydantic import ValidationError


def test_config_exactly_four_active_versioned_rules_and_checksum(rule_set):
    assert len(rule_set.opportunity_rules) == 4 and rule_set.status == "ACTIVE"
    assert rule_set.checksum() == rule_set.checksum() and len(rule_set.checksum()) == 64
    for rule in rule_set.opportunity_rules.values():
        ensure_relational_language(rule.model_dump(mode="json"))


def test_config_rejects_missing_rule_and_bad_priority(rule_set):
    raw = rule_set.model_dump(mode="python")
    raw["opportunity_rules"].pop("TRADE_FINANCE")
    with pytest.raises(ValidationError):
        RuleSetConfig.model_validate(raw)
    raw = rule_set.model_dump(mode="python")
    raw["priority"]["weights"]["confidence"] += 0.1
    with pytest.raises(ValidationError):
        RuleSetConfig.model_validate(raw)


def test_deterministic_uuid():
    assert deterministic_uuid("a", 1) == deterministic_uuid("a", 1)
    assert deterministic_uuid("a", 1) != deterministic_uuid("a", 2)


def test_audit_is_canonical_and_rejects_credit_decision_vocabulary():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
    ensure_relational_language({"type": "FINANCIAL_STRESS_SIGNAL", "what": "relational signal"})
    with pytest.raises(ValueError):
        ensure_relational_language({"what": "risk_score"})
    result = DecisionAuditBuilder().build(
        decision_id="d",
        opportunity={"type": "TRADE_FINANCE"},
        inputs={"x": 1},
        config_id="c",
        config_checksum="h",
        correlation_id="corr",
    )
    assert len(result["decision_hash"]) == 64 and result["correlation_id"] == "corr"


def test_replaceable_adapters_filter_and_status():
    customer = CanonicalCustomer("SME-1", "Synthetic", "SERVICES", "SMALL")
    account = CanonicalAccount("A1", "SME-1", "CURRENT", "MAD")
    core = InMemoryCoreBankingAdapter([customer], [account])
    assert core.fetch_customers() == (customer,) and core.fetch_accounts() == (account,)
    tx1 = CanonicalTransaction(
        "T1", "A1", date(2026, 1, 1), "CREDIT", Decimal(100), "MAD", "RECEIPT", False
    )
    tx2 = CanonicalTransaction(
        "T2", "A1", date(2026, 2, 1), "DEBIT", Decimal(50), "MAD", "PAYMENT", False
    )
    assert InMemoryPaymentAdapter([tx1, tx2]).fetch_transactions(
        date(2026, 1, 15), date(2026, 2, 2)
    ) == (tx2,)
    products = InMemoryProductAdapter({("SME-1", "TRADE_FINANCE"): "UNDERUTILIZED"})
    assert (
        products.product_status("SME-1", "TRADE_FINANCE") == "UNDERUTILIZED"
        and products.product_status("SME-2", "TRADE_FINANCE") == "ABSENT"
    )
