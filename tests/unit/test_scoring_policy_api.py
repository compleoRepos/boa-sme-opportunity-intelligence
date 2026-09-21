from __future__ import annotations

from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.models.entities import ScoringPolicy, ScoringPolicyAuditLog, ScoringPolicyVersion
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def policy_context(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, sessionmaker[Session]]:
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'opportunity'")
        for model in (ScoringPolicy, ScoringPolicyVersion, ScoringPolicyAuditLog):
            cast(Table, model.__mapper__.local_table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = application_for("opportunity-service")
    app.state.session_factory = factory
    return TestClient(app), factory


def test_policy_simulation_is_explicitly_not_implemented_and_keeps_draft(
    policy_context: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = policy_context
    headers = {"X-Correlation-ID": "policy-not-implemented-test"}
    created = client.post(
        "/internal/v1/scoring-policies",
        headers=headers,
        json={
            "policyId": "policy-simulation-contract",
            "weights": {"rules": 0.8, "ml": 0.2},
            "reason": "Vérifier le contrat de simulation sans chiffres inventés",
        },
    )
    assert created.status_code == 201

    response = client.post(
        "/internal/v1/scoring-policies/policy-simulation-contract/versions/1/simulate",
        headers=headers,
        json={
            "reason": "Calculer une comparaison avant après déterministe",
            "simulationId": "simulation-not-persisted",
        },
    )

    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert body["details"] == [
        {
            "policyId": "policy-simulation-contract",
            "version": 1,
            "requiredOutputs": [
                "priorityDistributionBeforeAfter",
                "movementsUpDown",
                "top10Changes",
            ],
        }
    ]
    with factory() as session:
        version = session.scalar(
            select(ScoringPolicyVersion).where(ScoringPolicyVersion.version == 1)
        )
        assert version is not None
        assert version.status == "DRAFT"
        assert version.simulation_id is None
        assert (
            session.query(ScoringPolicyAuditLog)
            .filter(ScoringPolicyAuditLog.action == "SIMULATED")
            .count()
            == 0
        )


def test_policy_simulation_rejects_deprecated_client_sample(
    policy_context: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = policy_context
    response = client.post(
        "/internal/v1/scoring-policies/missing/versions/1/simulate",
        headers={"X-Correlation-ID": "policy-sample-rejected"},
        json={
            "reason": "Ne pas accepter des résultats calculés par le client",
            "sample": {"promoted": 42},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["details"][0]["field"] == "body.sample"
    assert response.json()["details"][0]["code"] == "extra_forbidden"
    assert response.json()["details"][0]["message"] == "Extra inputs are not permitted"
