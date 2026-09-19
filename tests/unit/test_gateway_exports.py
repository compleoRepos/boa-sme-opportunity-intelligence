from __future__ import annotations

from typing import Any

import pytest
from boa_oi import gateway_api
from boa_oi.api import application_for
from boa_oi.http_clients import ServiceBinaryResponse
from boa_oi.platform import Principal, current_principal
from fastapi.testclient import TestClient


def principal(role: str) -> Principal:
    return Principal(
        subject=f"subject-{role.lower()}",
        username=role.lower(),
        roles={role},
        scopes=set(),
        client_id="boa-sme-spa",
        relationship_manager_ids=("rm-01",) if role == "RELATIONSHIP_MANAGER" else (),
        branch_ids=("BR-01",) if role == "BRANCH_MANAGER" else (),
        customer_scopes=(),
    )


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    yield
    application_for("api-gateway").dependency_overrides.clear()


def test_gateway_proxies_xlsx_bytes_filters_and_controlled_headers(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_binary(method: str, url: str, **kwargs: Any) -> ServiceBinaryResponse:
        captured.update({"method": method, "url": url, **kwargs})
        return ServiceBinaryResponse(
            content=b"PK\x03\x04workbook",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content_disposition='attachment; filename="opportunites.xlsx"',
            sha256="a" * 64,
        )

    monkeypatch.setenv("OPPORTUNITY_SERVICE_URL", "http://opportunity:8080")
    monkeypatch.setattr(gateway_api, "service_binary_request", fake_binary)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("RELATIONSHIP_MANAGER")

    response = TestClient(app).get(
        "/api/v1/exports/opportunities.xlsx?status=OPEN&priorityLevel=P1",
        headers={"X-Correlation-ID": "corr-gateway-export"},
    )

    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert response.headers["content-disposition"] == 'attachment; filename="opportunites.xlsx"'
    assert response.headers["x-content-sha256"] == "a" * 64
    assert captured["url"].endswith("/internal/v1/exports/opportunities.xlsx")
    assert captured["params"] == {"status": "OPEN", "priorityLevel": "P1"}


def test_gateway_portfolio_export_is_limited_to_commercial_roles(monkeypatch) -> None:
    called = False

    async def fake_binary(*_args: Any, **_kwargs: Any) -> ServiceBinaryResponse:
        nonlocal called
        called = True
        return ServiceBinaryResponse(
            content=b"PK",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content_disposition=None,
            sha256=None,
        )

    monkeypatch.setattr(gateway_api, "service_binary_request", fake_binary)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("ADMIN")

    response = TestClient(app).get("/api/v1/exports/portfolio.xlsx")

    assert response.status_code == 403
    assert called is False


def test_gateway_openapi_documents_export_contracts() -> None:
    paths = application_for("api-gateway").openapi()["paths"]
    assert "/api/v1/exports/opportunities.xlsx" in paths
    assert "/api/v1/exports/portfolio.xlsx" in paths
