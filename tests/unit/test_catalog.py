"""Catalogue commercial BANK OF AFRICA : cohérence et statut par famille."""

from collections import Counter

from boa_oi.catalog import (
    BOA_PRODUCTS,
    FAMILIES,
    PRODUCTS_BY_FAMILY,
    as_payload,
    demo_ownerships,
    family_status,
)
from boa_oi.technical.config import load_rule_set


def test_catalog_is_consistent():
    codes = [item.code for item in BOA_PRODUCTS]
    assert len(codes) == 28
    assert len(codes) == len(set(codes))
    assert all(item.family in FAMILIES for item in BOA_PRODUCTS)
    assert all(item.source_url.startswith("https://www.bankofafrica.ma/") for item in BOA_PRODUCTS)
    assert all(item.description for item in BOA_PRODUCTS)
    assert all(PRODUCTS_BY_FAMILY[family] for family in FAMILIES), "chaque famille a un produit"
    assert {segment for item in BOA_PRODUCTS for segment in item.target_segments} <= {
        "SMALL",
        "MEDIUM",
        "ENTERPRISE",
        "LARGE",
        "PROFESSIONAL",
    }
    assert next(
        item for item in BOA_PRODUCTS if item.code == "BOA_ISTITMAR_MAROC_PME"
    ).target_segments == ("SMALL",)
    assert next(
        item for item in BOA_PRODUCTS if item.code == "BOA_CASH_POOLING"
    ).target_segments == (
        "LARGE",
        "ENTERPRISE",
    )
    assert all(
        item.target_segments == ("PROFESSIONAL",)
        for item in BOA_PRODUCTS
        if item.family in {"TERM_DEPOSIT", "LIQUIDITY_INVESTMENT"}
    )


def test_rule_set_recommends_catalog_products():
    rule_set = load_rule_set()
    known = {item.code for item in BOA_PRODUCTS}
    for rule in rule_set.opportunity_rules.values():
        assert set(rule.recommended_product_codes) <= known


def test_family_status_aggregates_ownership():
    gaps = [
        {"product": as_payload(PRODUCTS_BY_FAMILY["INVESTMENT_FINANCING"][0]), "status": "ABSENT"},
        {"product": as_payload(PRODUCTS_BY_FAMILY["INVESTMENT_FINANCING"][1]), "status": "OWNED"},
        {"product": as_payload(PRODUCTS_BY_FAMILY["TRADE_FINANCE"][0]), "status": "UNDERUTILIZED"},
        {
            "product": as_payload(PRODUCTS_BY_FAMILY["CASH_MANAGEMENT"][0]),
            "status": "ABSENT",
        },
        {
            "product": as_payload(PRODUCTS_BY_FAMILY["CASH_MANAGEMENT"][1]),
            "status": "ABSENT_OR_ELSEWHERE",
        },
        {"product": {"productId": "LEGACY", "name": "x", "category": "y"}, "status": "ABSENT"},
    ]
    status = family_status(gaps)
    assert status["INVESTMENT_FINANCING"] == "OWNED"
    assert status["TRADE_FINANCE"] == "UNDERUTILIZED"
    assert status["CASH_MANAGEMENT"] == "ABSENT_OR_ELSEWHERE"
    assert status["LEGACY"] == "ABSENT"
    assert status[PRODUCTS_BY_FAMILY["INVESTMENT_FINANCING"][0].code] == "ABSENT"


def test_demo_ownerships_keep_trade_gap_for_international_growth():
    for index in range(1, 501):
        ref = f"SME-{index:05d}"
        owned = demo_ownerships(ref, "INTERNATIONAL_GROWTH")
        families = {next(p.family for p in BOA_PRODUCTS if p.code == code) for code in owned}
        assert "TRADE_FINANCE" not in families
        assert len(owned) == len(families), "un seul produit par famille"
    assert demo_ownerships("SME-00001", "GROWTH_COMPANY") == demo_ownerships(
        "SME-00001", "GROWTH_COMPANY"
    )


def test_synthetic_branch_distribution_exercises_secondary_visibility_for_ahmed():
    from database.seed.generate import scenario_for
    from database.seed.naming import relationship_manager_index

    branch_distribution = Counter(relationship_manager_index(index) for index in range(1, 251))
    ahmed_secondary = [
        index
        for index in range(1, 251)
        if relationship_manager_index(index) == 1 and scenario_for(index) == "MULTIBANK_SECONDARY"
    ]

    assert sum(branch_distribution.values()) == 250
    assert set(branch_distribution) == {1, 2, 3, 4, 5}
    assert branch_distribution[1] == max(branch_distribution.values())
    assert ahmed_secondary, "le parcours E2E Ahmed doit exercer MULTIBANK_SECONDARY"
