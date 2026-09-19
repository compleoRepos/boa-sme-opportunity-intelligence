from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.models.entities import (
    Customer,
    Opportunity,
    OpportunityRule,
    PortfolioAssignment,
    RelationshipManager,
)
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def opportunity_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "true")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        RelationshipManager.__mapper__.local_table,
        Customer.__mapper__.local_table,
        PortfolioAssignment.__mapper__.local_table,
        OpportunityRule.__mapper__.local_table,
        Opportunity.__mapper__.local_table,
    ]
    with engine.connect() as connection:
        for schema in ("customer", "opportunity"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in tables:
            cast(Table, table).create(connection)

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    rm_one_id = deterministic_uuid("opportunity-filter-rm", "rm-01")
    rm_two_id = deterministic_uuid("opportunity-filter-rm", "rm-02")
    rule_id = deterministic_uuid("opportunity-filter-rule", "1")
    customers = (
        ("SME-00001", "AGRICULTURE", "SMALL", rm_one_id),
        ("SME-00002", "SERVICES", "MEDIUM", rm_one_id),
        ("SME-00003", "AGRICULTURE", "LARGE", rm_two_id),
    )
    with factory.begin() as session:
        session.add_all(
            [
                RelationshipManager(
                    id=rm_one_id,
                    subject_id="rm-01",
                    display_name="CC Un",
                    branch_code="BR-01",
                    active=True,
                ),
                RelationshipManager(
                    id=rm_two_id,
                    subject_id="rm-02",
                    display_name="CC Deux",
                    branch_code="BR-02",
                    active=True,
                ),
                OpportunityRule(
                    id=rule_id,
                    opportunity_type="TEST_OPPORTUNITY",
                    version="1",
                    configuration_json={},
                    active=True,
                ),
            ]
        )
        for index, (customer_ref, sector, segment, manager_id) in enumerate(customers, start=1):
            customer_id = deterministic_uuid("customer", customer_ref)
            active_manager_id = manager_id
            legacy_manager_id = rm_two_id if customer_ref == "SME-00002" else manager_id
            session.add(
                Customer(
                    id=customer_id,
                    customer_ref=customer_ref,
                    legal_name=f"Entreprise {index}",
                    sector_code=sector,
                    segment_code=segment,
                    scenario_code="NORMAL_CUSTOMER",
                    incorporated_on=date(2018, 1, 1),
                    status="ACTIVE",
                    rm_id=legacy_manager_id,
                )
            )
            session.add(
                PortfolioAssignment(
                    id=deterministic_uuid("opportunity-filter-assignment", customer_ref),
                    customer_id=customer_id,
                    relationship_manager_id=active_manager_id,
                    branch_code="BR-01" if active_manager_id == rm_one_id else "BR-02",
                    valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    valid_to=None,
                    actor="unit-test",
                    reason="Affectation active de test",
                )
            )
            session.add(
                Opportunity(
                    id=deterministic_uuid("opportunity-filter-row", index),
                    opportunity_ref=f"OPP-{index}",
                    customer_id=customer_id,
                    customer_ref=customer_ref,
                    customer_name=f"Entreprise {index}",
                    opportunity_type=("INVESTMENT_FINANCING" if index < 3 else "CASH_INVESTMENT"),
                    status="OPEN" if index < 3 else "DISMISSED",
                    horizon="1-3_MONTHS",
                    confidence_score=Decimal("0.90") - Decimal(index - 1) / Decimal("10"),
                    confidence_level="HIGH",
                    confidence_components_json=[],
                    priority_score=Decimal(100 - index),
                    priority_level="P1" if index < 3 else "P3",
                    priority_components_json=[],
                    why_json=[],
                    what_text="Tester les filtres",
                    when_text="Maintenant",
                    recommended_products_json=[],
                    explanation_json={"evidence": []},
                    generated_at=datetime(2026, 9, index, tzinfo=timezone.utc),
                    rule_id=rule_id,
                    deduplication_key=f"opportunity-filter-{index}",
                )
            )

    app = application_for("opportunity-service")
    app.state.session_factory = factory
    with TestClient(app) as client:
        yield client
    del app.state.session_factory
    engine.dispose()


def opportunity_ids(response) -> set[str]:
    assert response.status_code == 200
    return {item["opportunityId"] for item in response.json()["data"]}


def persona(
    role: str,
    *,
    relationship_manager_ids: list[str] | None = None,
    branch_ids: list[str] | None = None,
) -> dict[str, str]:
    return {
        "X-Dev-Principal": json.dumps(
            {
                "subject": f"scope-{role.lower()}",
                "username": f"scope-{role.lower()}",
                "roles": [role],
                "relationshipManagerIds": relationship_manager_ids or [],
                "branchIds": branch_ids or [],
            }
        )
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("sector=AGRICULTURE", {"OPP-1", "OPP-3"}),
        ("customerSegment=SMALL", {"OPP-1"}),
        ("customerSegment=SME", {"OPP-1", "OPP-2"}),
        ("relationshipManagerId=rm-01", {"OPP-1", "OPP-2"}),
    ],
)
def test_opportunity_filters_return_matching_customer_data(
    opportunity_client: TestClient,
    query: str,
    expected: set[str],
) -> None:
    response = opportunity_client.get(f"/internal/v1/opportunities?{query}&pageSize=100")

    assert opportunity_ids(response) == expected


@pytest.mark.parametrize(
    "query",
    [
        "sector=UNKNOWN",
        "customerSegment=UNKNOWN",
        "relationshipManagerId=unknown",
    ],
)
def test_opportunity_filters_exclude_non_matching_customer_data(
    opportunity_client: TestClient,
    query: str,
) -> None:
    response = opportunity_client.get(f"/internal/v1/opportunities?{query}&pageSize=100")

    assert opportunity_ids(response) == set()


def test_customer_filters_compose_with_existing_opportunity_filters(
    opportunity_client: TestClient,
) -> None:
    response = opportunity_client.get(
        "/internal/v1/opportunities"
        "?sector=AGRICULTURE"
        "&customerSegment=SME"
        "&relationshipManagerId=rm-01"
        "&opportunityType=INVESTMENT_FINANCING"
        "&status=OPEN"
        "&minConfidence=0.85"
        "&pageSize=100"
    )

    assert opportunity_ids(response) == {"OPP-1"}


def test_relationship_manager_scope_cannot_be_overridden_by_query(
    opportunity_client: TestClient,
) -> None:
    headers = persona("RELATIONSHIP_MANAGER", relationship_manager_ids=["rm-01"])

    scoped = opportunity_client.get("/internal/v1/opportunities?pageSize=100", headers=headers)
    attempted_escape = opportunity_client.get(
        "/internal/v1/opportunities?relationshipManagerId=rm-02&pageSize=100",
        headers=headers,
    )
    direct_escape = opportunity_client.get("/internal/v1/opportunities/OPP-3", headers=headers)

    assert opportunity_ids(scoped) == {"OPP-1", "OPP-2"}
    assert opportunity_ids(attempted_escape) == set()
    assert direct_escape.status_code == 404


def test_branch_manager_scope_is_enforced_on_list_and_detail(
    opportunity_client: TestClient,
) -> None:
    headers = persona("BRANCH_MANAGER", branch_ids=["BR-02"])

    scoped = opportunity_client.get("/internal/v1/opportunities?pageSize=100", headers=headers)
    direct_escape = opportunity_client.get("/internal/v1/opportunities/OPP-1", headers=headers)

    assert opportunity_ids(scoped) == {"OPP-3"}
    assert direct_escape.status_code == 404


def test_relationship_manager_without_scope_is_forbidden(
    opportunity_client: TestClient,
) -> None:
    response = opportunity_client.get(
        "/internal/v1/opportunities",
        headers=persona("RELATIONSHIP_MANAGER"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PORTFOLIO_SCOPE_MISSING"
