from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.models.entities import (
    Customer,
    FlowVisibilitySnapshot,
    Opportunity,
    OpportunityAction,
    PropensityScoreRecord,
    RelationshipManager,
)
from boa_oi.platform import Principal, current_principal
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    yield
    for service in ("portfolio-service", "customer-service"):
        application_for(service).dependency_overrides.clear()


def principal(role: str, *, managers: tuple[str, ...] = (), branches: tuple[str, ...] = ()):
    return Principal(
        subject=f"subject-{role.lower()}",
        username=role.lower(),
        roles={role},
        scopes=set(),
        client_id="boa-sme-spa",
        relationship_manager_ids=managers,
        branch_ids=branches,
        customer_scopes=("assigned" if role == "RELATIONSHIP_MANAGER" else "branch",),
    )


def factory_and_ids():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        RelationshipManager.__mapper__.local_table,
        Customer.__mapper__.local_table,
        FlowVisibilitySnapshot.__mapper__.local_table,
        PropensityScoreRecord.__mapper__.local_table,
        Opportunity.__mapper__.local_table,
        OpportunityAction.__mapper__.local_table,
    ]
    with engine.connect() as connection:
        for schema in ("customer", "analytics", "ml", "opportunity", "action"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in tables:
            cast(Table, table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    rm1 = deterministic_uuid("rm", 1)
    rm2 = deterministic_uuid("rm", 2)
    rm3 = deterministic_uuid("rm", 3)
    customers = {
        "SME-00001": (deterministic_uuid("customer", "SME-00001"), rm1),
        "SME-00002": (deterministic_uuid("customer", "SME-00002"), rm2),
        "SME-00003": (deterministic_uuid("customer", "SME-00003"), rm3),
    }
    with factory.begin() as session:
        session.add_all(
            [
                RelationshipManager(
                    id=rm1,
                    subject_id="rm-01",
                    display_name="CC Un",
                    branch_code="BR-01",
                    active=True,
                ),
                RelationshipManager(
                    id=rm2,
                    subject_id="rm-02",
                    display_name="CC Deux",
                    branch_code="BR-01",
                    active=True,
                ),
                RelationshipManager(
                    id=rm3,
                    subject_id="rm-03",
                    display_name="CC Trois",
                    branch_code="BR-02",
                    active=True,
                ),
            ]
        )
        for customer_ref, (customer_id, manager_id) in customers.items():
            session.add(
                Customer(
                    id=customer_id,
                    customer_ref=customer_ref,
                    legal_name=f"Entreprise {customer_ref}",
                    sector_code="TRADE",
                    segment_code="MEDIUM",
                    scenario_code="NORMAL_CUSTOMER",
                    incorporated_on=date(2018, 1, 1),
                    status="ACTIVE",
                    rm_id=manager_id,
                )
            )
            session.add(
                PropensityScoreRecord(
                    id=deterministic_uuid("score", customer_ref),
                    customer_id=customer_id,
                    customer_ref=customer_ref,
                    as_of_date=date(2026, 9, 30),
                    score_type="SALES_PROPENSITY",
                    score=Decimal("0.90") if customer_ref == "SME-00001" else Decimal("0.20"),
                    threshold=Decimal("0.58"),
                    above_threshold=customer_ref == "SME-00001",
                    score_band="HIGH" if customer_ref == "SME-00001" else "LOW",
                    segment="MEDIUM",
                    model_version="sales-propensity-logit-poc-v1",
                    feature_set_version="sales-features-v2",
                    feature_checksum=("a" if customer_ref == "SME-00001" else "b") * 64,
                    contributions_json=[],
                    top_factors_json=[],
                    training_dataset_version="synthetic-demo-20260918-v1",
                    deployment_mode="POC_SHADOW",
                    created_by="unit-test",
                )
            )
        session.add_all(
            [
                FlowVisibilitySnapshot(
                    id=deterministic_uuid("flow-visibility", "SME-00001"),
                    customer_id=customers["SME-00001"][0],
                    customer_ref="SME-00001",
                    as_of_date=date(2026, 9, 30),
                    level="HIGH",
                    estimated_share=Decimal("0.82"),
                    method="TURNOVER_RATIO",
                    evidence_json=[{"fact": "TURNOVER_RATIO", "value": 0.82}],
                    fingerprint_count_90d=0,
                    fingerprint_previous_90d=0,
                    categorization_coverage=Decimal("1.0"),
                    calculation_version="visibility-v1",
                    input_watermark="unit-test-high",
                    created_by="unit-test",
                ),
                FlowVisibilitySnapshot(
                    id=deterministic_uuid("flow-visibility", "SME-00002"),
                    customer_id=customers["SME-00002"][0],
                    customer_ref="SME-00002",
                    as_of_date=date(2026, 9, 30),
                    level="LOW",
                    estimated_share=Decimal("0.25"),
                    method="DECLARED",
                    evidence_json=[{"fact": "BANKING_RELATIONSHIP_DECLARED"}],
                    fingerprint_count_90d=2,
                    fingerprint_previous_90d=1,
                    categorization_coverage=Decimal("0.95"),
                    calculation_version="visibility-v1",
                    input_watermark="unit-test-low",
                    created_by="unit-test",
                ),
            ]
        )
    return factory, customers


def client_for(service: str, factory, identity: Principal) -> TestClient:
    app = application_for(service)
    app.state.session_factory = factory
    app.dependency_overrides[current_principal] = lambda: identity
    return TestClient(app)


def test_cc_cannot_escape_own_portfolio_with_query_parameters(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    factory, _customers = factory_and_ids()
    rm = principal("RELATIONSHIP_MANAGER", managers=("rm-01",), branches=("BR-01",))

    portfolio_client = client_for("portfolio-service", factory, rm)
    dashboard = portfolio_client.get("/internal/v1/dashboards/me?relationshipManagerId=rm-02")
    assert dashboard.status_code == 200
    assert [item["customerId"] for item in dashboard.json()["portfolio"]] == ["SME-00001"]

    customer_client = client_for("customer-service", factory, rm)
    malicious_list = customer_client.get(
        "/internal/v1/customers?relationshipManagerId=rm-02&pageSize=100"
    )
    assert malicious_list.status_code == 200
    assert malicious_list.json()["data"] == []
    own_search = customer_client.get("/internal/v1/customers?q=SME-000&pageSize=1")
    assert own_search.status_code == 200
    assert own_search.json()["meta"]["totalCount"] is None
    assert [item["customerId"] for item in own_search.json()["data"]] == ["SME-00001"]
    forbidden_detail = customer_client.get("/internal/v1/customers/SME-00002")
    assert forbidden_detail.status_code == 404

    forbidden_declaration = customer_client.put(
        "/internal/v1/customers/SME-00002/banking-relationship",
        json={
            "bankingRelationship": "SECONDARY",
            "reason": "Déclaration confirmée pendant l'entretien client.",
        },
    )
    assert forbidden_declaration.status_code == 403
    assert forbidden_declaration.json()["code"] == "CUSTOMER_OUTSIDE_PORTFOLIO"


def test_branch_scope_is_consolidated_but_cannot_cross_branch(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    factory, _customers = factory_and_ids()
    branch = principal("BRANCH_MANAGER", branches=("BR-01",))
    portfolio_client = client_for("portfolio-service", factory, branch)

    dashboard = portfolio_client.get("/internal/v1/dashboards/branch")
    assert dashboard.status_code == 200
    assert dashboard.json()["kpis"]["portfolioCustomers"] == 2
    assert {item["relationshipManagerId"] for item in dashboard.json()["relationshipManagers"]} == {
        "rm-01",
        "rm-02",
    }
    assert dashboard.json()["visibilityDistribution"] == [
        {"level": "HIGH", "count": 1, "share": 0.5},
        {"level": "PARTIAL", "count": 0, "share": 0.0},
        {"level": "LOW", "count": 1, "share": 0.5},
        {"level": "UNKNOWN", "count": 0, "share": 0.0},
    ]
    rm_one = portfolio_client.get("/internal/v1/dashboards/relationship-managers/rm-01")
    rm_two = portfolio_client.get("/internal/v1/dashboards/relationship-managers/rm-02")
    assert {
        item["customerId"]: item["flowVisibility"]
        for item in rm_one.json()["portfolio"] + rm_two.json()["portfolio"]
    } == {
        "SME-00001": {
            "level": "HIGH",
            "estimatedShare": 0.82,
            "method": "TURNOVER_RATIO",
            "asOf": "2026-09-30",
        },
        "SME-00002": {
            "level": "LOW",
            "estimatedShare": 0.25,
            "method": "DECLARED",
            "asOf": "2026-09-30",
        },
    }
    cross_branch = portfolio_client.get("/internal/v1/dashboards/relationship-managers/rm-03")
    assert cross_branch.status_code == 404


def test_shadow_propensity_does_not_change_rules_only_priority(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    factory, _customers = factory_and_ids()
    branch = principal("BRANCH_MANAGER", branches=("BR-01",))
    portfolio_client = client_for("portfolio-service", factory, branch)
    dashboard = portfolio_client.get("/internal/v1/dashboards/branch")
    assert dashboard.status_code == 200

    rm1 = portfolio_client.get("/internal/v1/dashboards/relationship-managers/rm-01").json()
    rm2 = portfolio_client.get("/internal/v1/dashboards/relationship-managers/rm-02").json()
    assert rm1["portfolio"][0]["propensityScore"] > rm2["portfolio"][0]["propensityScore"]
    assert rm1["portfolio"][0]["combinedPriorityScore"] == 0
    assert rm2["portfolio"][0]["combinedPriorityScore"] == 0
    assert rm1["portfolio"][0]["priorityLevel"] == "P4"
    assert rm2["portfolio"][0]["priorityLevel"] == "P4"


def test_propensity_as_of_excludes_future_score(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    factory, customers = factory_and_ids()
    with factory.begin() as session:
        session.add(
            PropensityScoreRecord(
                id=deterministic_uuid("score", "SME-00001", "future"),
                customer_id=customers["SME-00001"][0],
                customer_ref="SME-00001",
                as_of_date=date(2026, 10, 31),
                score_type="SALES_PROPENSITY",
                score=Decimal("0.99"),
                threshold=Decimal("0.58"),
                above_threshold=True,
                score_band="HIGH",
                segment="MEDIUM",
                model_version="future-model-must-not-leak",
                feature_set_version="future-features-must-not-leak",
                feature_checksum="f" * 64,
                contributions_json=[],
                top_factors_json=[],
                training_dataset_version="future-dataset-must-not-leak",
                deployment_mode="POC_SHADOW",
                created_by="unit-test",
            )
        )

    identity = principal("BRANCH_MANAGER", branches=("BR-01",))
    response = client_for("portfolio-service", factory, identity).get(
        "/internal/v1/customers/SME-00001/propensity",
        params={"asOf": "2026-09-30"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["asOf"] == "2026-09-30"
    assert payload["model"]["modelVersion"] == "sales-propensity-logit-poc-v1"
    assert payload["model"]["trainingDatasetVersion"] == "synthetic-demo-20260918-v1"


def test_propensity_as_of_excludes_future_opportunity(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    factory, customers = factory_and_ids()
    with factory.begin() as session:
        session.add(
            Opportunity(
                id=deterministic_uuid("opportunity", "SME-00001", "future"),
                opportunity_ref="OPP-FUTURE-MUST-NOT-LEAK",
                customer_id=customers["SME-00001"][0],
                customer_ref="SME-00001",
                customer_name="Entreprise SME-00001",
                opportunity_type="FUTURE_RULE",
                status="OPEN",
                status_updated_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                status_reason=None,
                expires_at=None,
                cooldown_until=None,
                last_action_at=None,
                horizon="30D",
                confidence_score=Decimal("0.99"),
                confidence_level="HIGH",
                confidence_components_json=[],
                priority_score=Decimal("99"),
                priority_level="P1",
                priority_components_json=[],
                why_json=[],
                what_text="Future opportunity",
                when_text="After asOf",
                recommended_products_json=[],
                recommendation_nature="NEED_DISCOVERY",
                explanation_json={},
                generated_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                engine_version="future-engine",
                rule_version="future-rule",
                scoring_policy_id="future-policy",
                scoring_policy_version=1,
                rules_weight=Decimal("1"),
                ml_weight=Decimal("0"),
                fallback_mode="RULES_ONLY",
                fallback_cause_json=None,
                rule_id=deterministic_uuid("rule", "future"),
                deduplication_key="future-opportunity-must-not-leak",
            )
        )

    identity = principal("BRANCH_MANAGER", branches=("BR-01",))
    response = client_for("portfolio-service", factory, identity).get(
        "/internal/v1/customers/SME-00001/propensity",
        params={"asOf": "2026-09-30"},
    )
    assert response.status_code == 200
    combination = response.json()["combination"]
    assert combination["rulesScore"] == 0
    assert combination["combinedPriorityScore"] == 0
    assert combination["policyId"] is None
    assert response.json()["priorityLevel"] == "P4"


def test_shadow_propensity_does_not_break_rules_only_priority_ties(monkeypatch):
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    factory, customers = factory_and_ids()
    rm1 = deterministic_uuid("rm", 1)
    with factory.begin() as session:
        customer_two = session.get(Customer, customers["SME-00002"][0])
        assert customer_two is not None
        customer_two.rm_id = rm1
        score_one = session.scalar(
            select(PropensityScoreRecord).where(PropensityScoreRecord.customer_ref == "SME-00001")
        )
        score_two = session.scalar(
            select(PropensityScoreRecord).where(PropensityScoreRecord.customer_ref == "SME-00002")
        )
        assert score_one is not None and score_two is not None
        score_one.score = Decimal("0.01")
        score_two.score = Decimal("0.99")

    branch = principal("BRANCH_MANAGER", branches=("BR-01",))
    portfolio_client = client_for("portfolio-service", factory, branch)
    payload = portfolio_client.get("/internal/v1/dashboards/relationship-managers/rm-01").json()
    assert [item["customerId"] for item in payload["portfolio"]] == [
        "SME-00001",
        "SME-00002",
    ]
    assert [item["combinedPriorityScore"] for item in payload["portfolio"]] == [0, 0]
