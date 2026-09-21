from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from boa_oi.api import application_for
from boa_oi.models.entities import (
    Opportunity,
    ScoringPolicy,
    ScoringPolicyAuditLog,
    ScoringPolicyVersion,
)
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
        for model in (ScoringPolicy, ScoringPolicyVersion, ScoringPolicyAuditLog, Opportunity):
            cast(Table, model.__mapper__.local_table).create(connection)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = application_for("opportunity-service")
    app.state.session_factory = factory
    return TestClient(app), factory


def test_policy_simulation_uses_persisted_shadow_scores_and_marks_version_simulated(
    policy_context: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = policy_context
    headers = {"X-Correlation-ID": "policy-simulation-test"}
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
    version_created = client.post(
        "/internal/v1/scoring-policies/policy-simulation-contract/versions",
        headers={"X-Correlation-ID": "policy-version-test"},
        json={
            "weights": {"rules": 0.8, "ml": 0.2},
            "reason": "Créer une version distincte pour la simulation",
        },
    )
    assert version_created.status_code == 201
    assert version_created.json()["policyId"] == "policy-simulation-contract"
    assert version_created.json()["version"] == 2
    with factory() as session:
        session.add(
            Opportunity(
                opportunity_ref="OPP-SIMULATION-001",
                customer_id=uuid4(),
                customer_ref="SME-SIMULATION-001",
                customer_name="PME simulation",
                opportunity_type="GROWTH_REVIEW",
                status="OPEN",
                horizon="0-3_MONTHS",
                confidence_score=Decimal("0.9"),
                confidence_level="HIGH",
                confidence_components_json=[],
                priority_score=Decimal("79"),
                priority_level="P2",
                priority_components_json=[],
                why_json=[],
                what_text="Examiner l'opportunité commerciale.",
                when_text="Dans les trois mois.",
                recommended_products_json=[],
                explanation_json={
                    "propensityShadow": {"propensity": 1.0, "deploymentMode": "POC_SHADOW"}
                },
                generated_at=datetime.now(timezone.utc),
                engine_version="test",
                rule_version="test",
                scoring_policy_id="commercial-rules-shadow-poc",
                scoring_policy_version=1,
                rules_weight=Decimal("1"),
                ml_weight=Decimal("0"),
                fallback_mode="RULES_ONLY",
                rule_id=uuid4(),
                deduplication_key="simulation-test",
            )
        )
        session.commit()

    response = client.post(
        "/internal/v1/scoring-policies/policy-simulation-contract/versions/2/simulate",
        headers=headers,
        json={
            "reason": "Calculer une comparaison avant après déterministe",
            "simulationId": "simulation-persisted",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["policyId"] == "policy-simulation-contract"
    assert body["status"] == "SIMULATED"
    assert body["simulationId"] == "simulation-persisted"
    assert body["simulation"]["source"] == "PERSISTED_OPPORTUNITIES_WITH_ML_SHADOW"
    assert body["simulation"]["sampleCount"] == 1
    assert body["simulation"]["movements"] == {"up": 1, "down": 0, "unchanged": 0}
    assert body["simulation"]["priorityDistribution"]["before"]["P2"] == 1
    assert body["simulation"]["priorityDistribution"]["after"]["P1"] == 1
    assert body["simulation"]["top10Changes"][0]["opportunityId"] == "OPP-SIMULATION-001"
    assert body["simulation"]["limitations"] == [
        "POC_SHADOW_ONLY",
        "SYNTHETIC_DATA_NOT_PRODUCTION_PERFORMANCE",
        "NO_CREDIT_DECISION",
    ]
    with factory() as session:
        version = session.scalar(
            select(ScoringPolicyVersion).where(ScoringPolicyVersion.version == 2)
        )
        assert version is not None
        assert version.status == "SIMULATED"
        assert version.simulation_id == "simulation-persisted"
        audit = session.scalar(
            select(ScoringPolicyAuditLog).where(ScoringPolicyAuditLog.action == "SIMULATED")
        )
        assert audit is not None
        assert audit.new_value_json is not None
        assert audit.new_value_json["simulation"]["sampleCount"] == 1
        opportunity = session.scalar(
            select(Opportunity).where(Opportunity.opportunity_ref == "OPP-SIMULATION-001")
        )
        assert opportunity is not None
        assert float(opportunity.priority_score) == 79.0
        assert opportunity.priority_level == "P2"
        assert float(opportunity.rules_weight) == 1.0
        assert float(opportunity.ml_weight) == 0.0


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


def test_policy_simulation_refuses_to_invent_results_without_shadow_scores(
    policy_context: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = policy_context
    headers = {"X-Correlation-ID": "policy-no-simulation-data"}
    created = client.post(
        "/internal/v1/scoring-policies",
        headers=headers,
        json={
            "policyId": "policy-without-scores",
            "weights": {"rules": 0.9, "ml": 0.1},
            "reason": "Vérifier le refus sans donnée persistée",
        },
    )
    assert created.status_code == 201

    response = client.post(
        "/internal/v1/scoring-policies/policy-without-scores/versions/1/simulate",
        headers=headers,
        json={"reason": "Ne jamais fabriquer une simulation"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SIMULATION_DATA_UNAVAILABLE"
    with factory() as session:
        version = session.scalar(
            select(ScoringPolicyVersion).where(ScoringPolicyVersion.version == 1)
        )
        assert version is not None
        assert version.status == "DRAFT"
        assert (
            session.query(ScoringPolicyAuditLog)
            .filter(ScoringPolicyAuditLog.action == "SIMULATED")
            .count()
            == 0
        )
