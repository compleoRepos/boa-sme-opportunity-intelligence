from __future__ import annotations

from typing import Any

import pytest
from boa_oi import gateway_api
from boa_oi.api import application_for
from boa_oi.platform import Principal, current_principal
from fastapi.testclient import TestClient


def principal(role: str) -> Principal:
    return Principal(
        subject=f"subject-{role.lower()}",
        username=role.lower(),
        roles={role},
        scopes=set(),
        client_id="boa-sme-spa",
        relationship_manager_ids=(),
        branch_ids=(),
        customer_scopes=(),
    )


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    yield
    application_for("api-gateway").dependency_overrides.clear()


def test_gateway_exposes_admin_sync_and_propagates_idempotency(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_service_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return {"jobId": "job-001", "status": "COMPLETED", "replayed": False}

    monkeypatch.setenv("CUSTOMER_SERVICE_URL", "http://customer:8080")
    monkeypatch.setattr(gateway_api, "service_request", fake_service_request)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("ADMIN")
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/portfolio-assignments/sync",
        headers={"Idempotency-Key": "gateway-sync-key"},
        json={"contractVersion": "1.0", "assignments": []},
    )

    assert response.status_code == 202
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/internal/v1/portfolio-assignments/sync")
    assert captured["idempotency_key"] == "gateway-sync-key"


def test_gateway_denies_commercial_role_before_proxy(monkeypatch):
    called = False

    async def fake_service_request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(gateway_api, "service_request", fake_service_request)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("RELATIONSHIP_MANAGER")
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/portfolio-assignments/sync",
        headers={"Idempotency-Key": "gateway-sync-denied"},
        json={"contractVersion": "1.0", "assignments": []},
    )

    assert response.status_code == 403
    assert called is False


def test_gateway_proxies_banking_relationship_declaration(monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_service_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        captured.update({"method": method, "url": url, **kwargs})
        return {
            "customerId": "SME-00042",
            "bankingRelationship": "SECONDARY",
            "flowVisibility": {"level": "UNKNOWN", "method": "NONE"},
        }

    monkeypatch.setenv("CUSTOMER_SERVICE_URL", "http://customer:8080")
    monkeypatch.setattr(gateway_api, "service_request", fake_service_request)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("RELATIONSHIP_MANAGER")
    client = TestClient(app)
    payload = {
        "bankingRelationship": "SECONDARY",
        "reason": "Déclaration confirmée pendant l'entretien client.",
    }

    response = client.put(
        "/api/v1/customers/SME-00042/banking-relationship",
        headers={"Authorization": "Bearer unit-test", "X-Dev-Principal": "ahmed"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["bankingRelationship"] == "SECONDARY"
    assert captured["method"] == "PUT"
    assert captured["url"] == (
        "http://customer:8080/internal/v1/customers/SME-00042/banking-relationship"
    )
    assert captured["json"] == payload
    assert captured["incoming_authorization"] == "Bearer unit-test"
    assert captured["dev_principal"] == "ahmed"


def test_gateway_openapi_documents_portfolio_sync_contract():
    paths = application_for("api-gateway").openapi()["paths"]
    assert "/api/v1/admin/portfolio-assignments/sync" in paths
    assert "post" in paths["/api/v1/admin/portfolio-assignments/sync"]
    assert "/api/v1/admin/portfolio-assignments" in paths
    assert "get" in paths["/api/v1/admin/portfolio-assignments"]
    assert "/api/v1/customers/{customer_id}/banking-relationship" in paths
    assert "put" in paths["/api/v1/customers/{customer_id}/banking-relationship"]
