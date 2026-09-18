from __future__ import annotations

from boa_oi.api import application_for
from boa_oi.http_clients import HttpBankingAdapter
from fastapi.testclient import TestClient

SERVICES = (
    "api-gateway",
    "customer-service",
    "account-service",
    "transaction-service",
    "mock-banking-api",
    "banking-integration-service",
    "analytics-service",
    "signal-service",
    "opportunity-service",
    "product-service",
    "action-service",
)


def test_each_service_is_a_distinct_fastapi_app_with_operations(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    apps = [application_for(service) for service in SERVICES]
    assert len({id(app) for app in apps}) == len(SERVICES)
    for service, app in zip(SERVICES, apps, strict=True):
        client = TestClient(app, raise_server_exceptions=False)
        correlation = f"corr-{service}"
        response = client.get("/health", headers={"X-Correlation-ID": correlation})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == correlation
        assert client.get("/swagger").status_code == 200
        spec = client.get("/openapi.json").json()
        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"] == f"BOA {service}"
        assert {"/health", "/ready", "/metrics"} <= set(spec["paths"])
        assert "oidc" in spec["components"]["securitySchemes"]


def test_auth_is_required_unless_explicit_test_switch(monkeypatch):
    monkeypatch.delenv("BOA_AUTH_DISABLED", raising=False)
    response = TestClient(application_for("customer-service"), raise_server_exceptions=False).get(
        "/internal/v1/customers"
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert "correlationId" in response.json()

    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    response = TestClient(application_for("customer-service"), raise_server_exceptions=False).get(
        "/internal/v1/customers?unknown=1"
    )
    assert response.status_code in {400, 503}
    if response.status_code == 400:
        assert response.json()["code"] == "UNKNOWN_FILTER"


def test_mock_banking_api_serves_facts_only(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    client = TestClient(application_for("mock-banking-api"))
    assert len(client.get("/mock/v1/customers?customerCount=2").json()) == 2
    transactions = client.get(
        "/mock/v1/transactions?customerCount=1&fromDate=2026-09-01&toDate=2026-09-03"
    ).json()
    assert transactions and all(
        "opportunity" not in key.lower() for row in transactions for key in row
    )
    products = client.get("/mock/v1/products?customerCount=2").json()
    assert products["products"] and "opportunities" not in products


def test_http_banking_adapter_uses_configured_remote_interface(monkeypatch):
    monkeypatch.setenv("MOCK_BANK_URL", "http://mock-bank:8080")
    adapter = HttpBankingAdapter()
    assert adapter.base_url == "http://mock-bank:8080"


def test_gateway_registers_all_frontend_routes(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    paths = set(application_for("api-gateway").openapi()["paths"])
    required = {
        "/api/v1/metrics/dashboard",
        "/api/v1/opportunities",
        "/api/v1/opportunities/{opportunity_id}/explanation",
        "/api/v1/opportunities/{opportunity_id}/actions",
        "/api/v1/customers",
        "/api/v1/customers/{customer_id}/accounts",
        "/api/v1/customers/{customer_id}/products",
        "/api/v1/customers/{customer_id}/transactions",
        "/api/v1/customers/{customer_id}/metrics",
        "/api/v1/customers/{customer_id}/signals",
        "/api/v1/customers/{customer_id}/opportunities",
        "/api/v1/customers/{customer_id}/actions",
        "/api/v1/signals",
        "/api/v1/products",
        "/api/v1/actions",
        "/api/v1/admin/rules",
        "/api/v1/admin/engine",
        "/api/v1/admin/pipeline",
    }
    assert required <= paths
