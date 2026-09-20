from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.models.entities import (
    Customer,
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
        PropensityScoreRecord.__mapper__.local_table,
        Opportunity.__mapper__.local_table,
        OpportunityAction.__mapper__.local_table,
    ]
    with engine.connect() as connection:
        for schema in ("customer", "ml", "opportunity", "action"):
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
