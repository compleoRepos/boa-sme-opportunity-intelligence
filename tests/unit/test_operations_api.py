from __future__ import annotations

from boa_oi.operations.api import READINESS_COMPONENTS, router
from boa_oi.platform import get_session
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeSession:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, item: object) -> None:
        self.items.append(item)

    def scalars(self, statement):
        class Result:
            def __iter__(self_nonlocal):
                return iter(())

            def all(self_nonlocal):
                return []

        return Result()


def make_client() -> tuple[TestClient, FakeSession, FastAPI]:
    app = FastAPI()
    session = FakeSession()
    app.dependency_overrides[get_session] = lambda: session
    app.include_router(router)
    return TestClient(app), session, app


def test_router_exposes_prefixed_monitoring_and_readiness_routes(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    client, _, app = make_client()
    assert {
        "/internal/v1/monitoring/observations",
        "/internal/v1/monitoring/history",
        "/internal/v1/readiness",
    } <= set(app.openapi()["paths"])
    assert client.get("/internal/v1/readiness").json()["status"] == "BLOCKED"


def test_readiness_has_exact_components_and_never_infers_production(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    client, _, _ = make_client()
    payload = client.get("/internal/v1/readiness").json()
    assert [item["name"] for item in payload["components"]] == list(READINESS_COMPONENTS)
    assert set(payload["componentStatuses"]) == set(READINESS_COMPONENTS)
    assert payload["status"] == "BLOCKED"
    assert set(payload["blockingComponents"]) == set(READINESS_COMPONENTS)


def test_observation_uses_configurable_thresholds_and_persists_snapshot_and_audit(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    client, session, _ = make_client()
    response = client.post(
        "/internal/v1/monitoring/observations",
        json={
            "domain": "FEATURE",
            "metric": "psi",
            "value": 0.25,
            "thresholds": {"warning": 0.10, "critical": 0.20, "method": "PSI"},
            "traceId": "trace-test",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "CRITICAL"
    assert payload["domain"] == "FEATURE"
    assert payload["traceId"] == "trace-test"
    assert len(session.items) == 2
    assert session.items[0].__class__.__name__ == "MLMonitoringSnapshot"
    assert session.items[1].__class__.__name__ == "MLGovernanceAuditLog"


def test_history_is_filterable(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    client, _, _ = make_client()
    response = client.get("/internal/v1/monitoring/history?domain=DATA&limit=10")
    assert response.status_code == 200
    assert response.json()["meta"] == {"limit": 10, "count": 0, "domain": "DATA"}
