from __future__ import annotations

from typing import Any

import pytest
from boa_oi import gateway_api
from boa_oi.api import application_for
from boa_oi.platform import Principal, current_principal
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def principal(role: str) -> Principal:
    return Principal(
        subject=f"subject-{role.lower()}",
        username=role.lower(),
        roles={role},
        scopes=set(),
        client_id="boa-sme-spa",
        relationship_manager_ids=("rm-01",),
        branch_ids=("BR-01",),
        customer_scopes=("assigned",),
    )


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    application_for("api-gateway").dependency_overrides.clear()


def test_gateway_allows_commercial_label_read(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_proxy(request, service, path, **kwargs):
        captured.update({"service": service, "path": path, **kwargs})
        return JSONResponse({"labels": {"OPEN": "Ouvert"}, "data": []})

    monkeypatch.setattr(gateway_api, "proxy", fake_proxy)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("RELATIONSHIP_MANAGER")

    response = TestClient(app).get("/api/v1/labels")

    assert response.status_code == 200
    assert captured["service"] == "rule-management"
    assert captured["path"] == "labels"


def test_gateway_blocks_non_admin_label_update(monkeypatch) -> None:
    called = False

    async def fake_proxy(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(gateway_api, "proxy", fake_proxy)
    app = application_for("api-gateway")
    app.dependency_overrides[current_principal] = lambda: principal("BUSINESS_ANALYST")

    response = TestClient(app).put(
        "/api/v1/admin/labels/STATUS/OPEN",
        json={
            "label": "À traiter",
            "active": True,
            "expectedVersion": 1,
            "justification": "Terminologie validée",
        },
    )

    assert response.status_code == 403
    assert called is False
