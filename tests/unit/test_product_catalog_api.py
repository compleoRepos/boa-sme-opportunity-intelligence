from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from boa_oi.catalog import PRODUCTS_BY_CODE
from boa_oi.models.entities import Product
from boa_oi.platform import Problem, get_session
from boa_oi.product_api import app, assert_catalog_ready
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def product_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'product'")
    Product.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add_all(
            [
                Product(
                    id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                    product_code="BOA_TRADE_TEST",
                    name="Produit trade test",
                    category="TRADE",
                    family="TRADE_FINANCE",
                    description="Description publique de test.",
                    source_url="https://www.bankofafrica.ma/fr/entreprises/test",
                    eligibility_rules_json={},
                    target_segments_json=["ENTERPRISE"],
                    currencies_json=["MAD"],
                    active=True,
                    created_by="test",
                ),
                Product(
                    id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                    product_code="BOA_CASH_TEST",
                    name="Produit cash test",
                    category="CASH",
                    family="CASH_MANAGEMENT",
                    description="Description publique de test.",
                    source_url="https://www.bankofafrica.ma/fr/entreprises/test-cash",
                    eligibility_rules_json={},
                    target_segments_json=["ENTERPRISE"],
                    currencies_json=["MAD"],
                    active=True,
                    created_by="test",
                ),
                Product(
                    id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
                    product_code="BOA_CREDIT_DOCUMENTAIRE",
                    name="Crédit documentaire",
                    category="TRADE_FINANCE",
                    family=PRODUCTS_BY_CODE["BOA_CREDIT_DOCUMENTAIRE"].family,
                    description="Description publique de test.",
                    source_url=PRODUCTS_BY_CODE["BOA_CREDIT_DOCUMENTAIRE"].source_url,
                    eligibility_rules_json={},
                    target_segments_json=["ENTERPRISE"],
                    currencies_json=["MAD"],
                    active=False,
                    created_by="test",
                ),
            ]
        )

    def session_override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_product_family_filter_and_provenance_contract(product_client: TestClient) -> None:
    response = product_client.get("/internal/v1/products?family=TRADE_FINANCE&pageSize=100")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["totalCount"] is None
    assert payload["meta"]["hasMore"] is False
    assert [item["productId"] for item in payload["data"]] == ["BOA_TRADE_TEST"]
    assert payload["data"][0]["family"] == "TRADE_FINANCE"
    assert payload["data"][0]["sourceUrl"].startswith("https://www.bankofafrica.ma/")


def test_product_family_is_an_allowed_filter(product_client: TestClient) -> None:
    response = product_client.get("/internal/v1/products?family=UNKNOWN")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_customer_product_gap_enforces_scope_inside_product_service(
    product_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def deny_cross_portfolio(*args, **kwargs):
        raise Problem(404, "RESOURCE_NOT_FOUND", "Customer not found.")

    monkeypatch.setenv("CUSTOMER_SERVICE_URL", "http://customer.test")
    monkeypatch.setattr("boa_oi.product_api.service_request", deny_cross_portfolio)
    principal = json.dumps(
        {
            "subject": "rm-limited",
            "roles": ["RELATIONSHIP_MANAGER"],
            "relationshipManagerIds": ["rm-limited"],
        }
    )

    response = product_client.get(
        "/internal/v1/customers/SME-99999/product-gaps",
        headers={"X-Dev-Principal": principal},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_product_import_rejects_code_outside_governed_catalogue(
    product_client: TestClient,
) -> None:
    response = product_client.post(
        "/internal/v1/imports/products",
        headers={"Idempotency-Key": "catalog-import-test"},
        json={
            "externalBatchId": "batch-unknown-product",
            "products": [
                {
                    "productId": "BOA_UNGOVERNED",
                    "name": "Produit non gouverné",
                    "category": "TEST",
                    "family": "TRADE_FINANCE",
                    "sourceUrl": "https://example.invalid/product",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UNKNOWN_CATALOG_PRODUCT"


@pytest.mark.parametrize(
    ("product_id", "expected_code"),
    [
        ("BOA_UNGOVERNED", "UNKNOWN_CATALOG_PRODUCT"),
        ("BOA_FINANCEMENT_IMPORTATIONS", "OWNERSHIP_PRODUCT_UNAVAILABLE"),
        ("BOA_CREDIT_DOCUMENTAIRE", "OWNERSHIP_PRODUCT_UNAVAILABLE"),
    ],
)
def test_product_import_rejects_unavailable_ownership_product(
    product_client: TestClient,
    product_id: str,
    expected_code: str,
) -> None:
    response = product_client.post(
        "/internal/v1/imports/products",
        headers={"Idempotency-Key": f"ownership-{product_id.lower()}"},
        json={
            "externalBatchId": f"batch-{product_id.lower()}",
            "products": [],
            "ownerships": [
                {
                    "customerId": "SME-00001",
                    "productId": product_id,
                    "status": "ACTIVE",
                    "openedOn": "2026-01-01",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == expected_code


def test_product_readiness_rejects_database_without_governed_seed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'product'")
    Product.__table__.create(engine)

    with pytest.raises(Problem) as exc_info:
        assert_catalog_ready(engine)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "PRODUCT_CATALOG_NOT_READY"
    engine.dispose()
