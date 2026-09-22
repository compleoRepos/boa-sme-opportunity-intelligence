from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from boa_oi.visibility import (
    HYPOTHESIS_LABEL,
    VisibilityTransaction,
    estimate_flow_visibility,
    is_inter_bank_self_transfer,
)

AS_OF = date(2026, 9, 30)


def tx(
    observed_on: date,
    *,
    amount: str = "100",
    direction: str = "CREDIT",
    category: str = "CUSTOMER_RECEIPT",
    status: str = "BOOKED",
) -> VisibilityTransaction:
    return VisibilityTransaction(observed_on, direction, Decimal(amount), category, status)


def estimate(**overrides: Any):
    values: dict[str, Any] = {
        "as_of": AS_OF,
        "banking_relationship": None,
        "relationship_as_of": None,
        "declared_turnover": None,
        "turnover_as_of": None,
        "transactions": (),
    }
    values.update(overrides)
    return estimate_flow_visibility(**values)


def test_declared_relationship_has_priority_over_turnover_and_fingerprints():
    result = estimate(
        banking_relationship="SECONDARY",
        relationship_as_of=datetime(2026, 9, 1, tzinfo=timezone.utc),
        declared_turnover=Decimal("100"),
        turnover_as_of=AS_OF,
        transactions=(
            tx(AS_OF, amount="1000"),
            tx(AS_OF, category="INTER_BANK_SELF_TRANSFER"),
            tx(date(2026, 9, 1), category="INTER_BANK_SELF_TRANSFER"),
        ),
    )

    assert (result.level, result.estimated_share, result.method) == ("LOW", None, "DECLARED")
    assert result.evidence[0]["fact"] == "BANKING_RELATIONSHIP_DECLARED"


def test_turnover_ratio_is_bounded_and_precedes_transaction_fingerprints():
    high = estimate(
        declared_turnover=Decimal("100"),
        turnover_as_of=AS_OF,
        transactions=(tx(AS_OF, amount="130"),),
    )
    partial = estimate(
        declared_turnover=Decimal("1000"),
        turnover_as_of=AS_OF,
        transactions=(
            tx(AS_OF, amount="600"),
            tx(AS_OF, category="INTER_BANK_SELF_TRANSFER"),
            tx(date(2026, 9, 1), category="INTER_BANK_SELF_TRANSFER"),
        ),
    )
    low = estimate(
        declared_turnover=Decimal("1000"),
        turnover_as_of=AS_OF,
        transactions=(tx(AS_OF, amount="250"),),
    )

    assert (high.level, high.estimated_share, high.method) == ("HIGH", 1.0, "TURNOVER_RATIO")
    assert (partial.level, partial.estimated_share, partial.method) == (
        "PARTIAL",
        0.6,
        "TURNOVER_RATIO",
    )
    assert (low.level, low.estimated_share, low.method) == ("LOW", 0.25, "TURNOVER_RATIO")
    assert partial.evidence[-1]["status"] == HYPOTHESIS_LABEL


def test_high_threshold_is_inclusive():
    result = estimate(
        declared_turnover=Decimal("1000"),
        turnover_as_of=AS_OF,
        transactions=(tx(AS_OF, amount="700"),),
    )

    assert (result.level, result.estimated_share, result.method) == (
        "HIGH",
        0.7,
        "TURNOVER_RATIO",
    )


def test_future_declarations_are_ignored_for_point_in_time_estimate():
    result = estimate(
        banking_relationship="SECONDARY",
        relationship_as_of=datetime(2026, 10, 1, tzinfo=timezone.utc),
        declared_turnover=Decimal("1000"),
        turnover_as_of=date(2026, 10, 1),
        transactions=(
            tx(AS_OF, category="INTER_BANK_SELF_TRANSFER"),
            tx(date(2026, 9, 1), category="INTER_BANK_SELF_TRANSFER"),
        ),
    )

    assert (result.level, result.estimated_share, result.method) == (
        "PARTIAL",
        None,
        "TRANSACTION_FINGERPRINTS",
    )


def test_two_recent_fingerprints_mean_partial_but_absence_never_means_high():
    partial = estimate(
        transactions=(
            tx(AS_OF, category="INTER_BANK_SELF_TRANSFER"),
            tx(date(2026, 9, 1), category="INTER_BANK_SELF_TRANSFER"),
            tx(date(2026, 5, 1), category="INTER_BANK_SELF_TRANSFER"),
        )
    )
    unknown = estimate(transactions=(tx(AS_OF),))

    assert (partial.level, partial.method, partial.fingerprint_count_90d) == (
        "PARTIAL",
        "TRANSACTION_FINGERPRINTS",
        2,
    )
    assert (unknown.level, unknown.method) == ("UNKNOWN", "NONE")


def test_non_booked_transactions_do_not_inflate_visibility_or_coverage():
    result = estimate(
        declared_turnover=Decimal("1000"),
        turnover_as_of=AS_OF,
        transactions=(
            tx(AS_OF, amount="900", status="REJECTED"),
            tx(AS_OF, amount="800", status="COMPLETED"),
            tx(AS_OF, category="INTER_BANK_SELF_TRANSFER", status="COMPLETED"),
            tx(AS_OF, amount="250", status="BOOKED"),
        ),
    )

    assert (
        result.level,
        result.estimated_share,
        result.fingerprint_count_90d,
        result.categorization_coverage,
    ) == (
        "LOW",
        0.25,
        0,
        1.0,
    )


def test_inter_bank_self_transfer_requires_explicit_flag_or_name_evidence():
    assert is_inter_bank_self_transfer(
        legal_name="Atlas Industrie SARL",
        transaction_type="TRANSFER",
        counterparty_name="Compte Atlas Industrie autre banque",
    )
    assert is_inter_bank_self_transfer(
        legal_name="Atlas Industrie SARL",
        transaction_type="PAYMENT",
        externally_domiciled=True,
    )
    assert not is_inter_bank_self_transfer(
        legal_name="Atlas Industrie SARL",
        transaction_type="PAYMENT",
        counterparty_name="Atlas Industrie",
    )
    assert not is_inter_bank_self_transfer(
        legal_name="Atlas Industrie SARL",
        transaction_type="TRANSFER",
        counterparty_name="Fournisseur Horizon",
    )
