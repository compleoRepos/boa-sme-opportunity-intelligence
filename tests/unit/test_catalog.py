"""Catalogue commercial BANK OF AFRICA : cohérence et statut par famille."""

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
    assert len(codes) == len(set(codes))
    assert all(item.family in FAMILIES for item in BOA_PRODUCTS)
    assert all(item.source_url.startswith("https://www.bankofafrica.ma/") for item in BOA_PRODUCTS)
    assert all(item.description for item in BOA_PRODUCTS)
    assert all(PRODUCTS_BY_FAMILY[family] for family in FAMILIES), "chaque famille a un produit"


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
        {"product": {"productId": "LEGACY", "name": "x", "category": "y"}, "status": "ABSENT"},
    ]
    status = family_status(gaps)
    assert status["INVESTMENT_FINANCING"] == "OWNED"
    assert status["TRADE_FINANCE"] == "UNDERUTILIZED"
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
