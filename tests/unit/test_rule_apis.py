from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

from boa_oi.api import application_for
from boa_oi.models import Base
from boa_oi.models.entities import (
    Customer,
    FlowVisibilityPolicy,
    MetricSnapshot,
    RelationshipManager,
    RuleAuditLog,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

RULE_SERVICES = (
    "rule-management-service",
    "rule-engine-service",
    "rule-simulation-service",
)


def memory_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    rule_tables = [table for table in Base.metadata.sorted_tables if table.schema == "rule"]
    with engine.connect() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS 'rule'")
        Base.metadata.create_all(connection, tables=rule_tables)
    return sessionmaker(bind=engine, expire_on_commit=False)


def lifecycle_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    schemas = ("rule", "customer", "analytics")
    tables = [table for table in Base.metadata.sorted_tables if table.schema in schemas]
    with engine.connect() as connection:
        for schema in schemas:
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        Base.metadata.create_all(connection, tables=tables)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_rule_services_are_selectable_and_distinct(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    apps = [application_for(service) for service in RULE_SERVICES]
    assert len({id(app) for app in apps}) == 3
    for service, app in zip(RULE_SERVICES, apps, strict=True):
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == service


def test_draft_rule_is_never_evaluated(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    factory = memory_factory()
    management = application_for("rule-management-service")
    management.state.session_factory = factory
    engine = application_for("rule-engine-service")
    engine.state.session_factory = factory
    rule = {
        "ruleId": "DRAFT_ONLY",
        "name": "Draft rule",
        "conditions": [{"metric": "growth", "operator": ">", "value": 1}],
        "recommendation": {
            "opportunityType": "TEST",
            "products": ["BOA_CREDIT_MLTD_DIRECT"],
        },
    }
    created = TestClient(management).post("/internal/v1/rules", json=rule)
    assert created.status_code == 201
    assert created.json()["lifecycle"] == {
        "validityDays": 90,
        "dismissedCooldownDays": 30,
        "convertedCooldownDays": 180,
        "deferredCooldownDays": 30,
        "expiredCooldownDays": 7,
    }
    response = TestClient(engine).post(
        "/internal/v1/rules/evaluate",
        json={"customerId": "SME-1", "metrics": {"growth": 999}},
    )
    assert response.status_code == 200
    assert response.json() == {
        "matched": False,
        "customerId": "SME-1",
        "engineVersion": "rule-engine-0.1.0",
        "evaluatedRuleVersions": [],
        "matches": [],
    }


def test_rule_studio_rejects_invalid_lifecycle_policy(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    factory = memory_factory()
    management = application_for("rule-management-service")
    management.state.session_factory = factory
    rule = {
        "name": "Invalid lifecycle",
        "conditions": [{"metric": "growth", "operator": ">", "value": 1}],
        "recommendation": {
            "opportunityType": "TEST",
            "products": ["BOA_CREDIT_MLTD_DIRECT"],
        },
        "lifecycle": {
            "validityDays": 0,
            "dismissedCooldownDays": 30,
            "convertedCooldownDays": 180,
            "deferredCooldownDays": 30,
            "expiredCooldownDays": 7,
        },
    }

    response = TestClient(management).post("/internal/v1/rules", json=rule)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_rule_studio_rejects_unknown_catalog_product(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    factory = memory_factory()
    management = application_for("rule-management-service")
    management.state.session_factory = factory
    rule = {
        "name": "Unknown product",
        "conditions": [{"metric": "growth", "operator": ">", "value": 1}],
        "recommendation": {
            "opportunityType": "TEST",
            "products": ["INVESTMENT_FINANCING"],
        },
    }

    response = TestClient(management).post("/internal/v1/rules", json=rule)

    assert response.status_code == 422
    assert response.json()["code"] == "RULE_VALIDATION_FAILED"
    assert response.json()["details"] == [
        {
            "field": "rule",
            "code": "INVALID_RULE",
            "message": (
                "recommendation.products contains unknown catalogue codes: INVESTMENT_FINANCING"
            ),
        }
    ]


def test_flow_domiciliation_full_governed_lifecycle(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    factory = lifecycle_factory()
    manager_id = uuid4()
    customer_id = uuid4()
    with factory.begin() as session:
        session.add(
            RelationshipManager(
                id=manager_id,
                subject_id="rm-flow",
                display_name="Ahmed Test",
                branch_code="BR-01",
                active=True,
            )
        )
        session.add(
            Customer(
                id=customer_id,
                customer_ref="SME-FLOW-001",
                legal_name="PME Domiciliation Synthétique",
                sector_code="SERVICES",
                segment_code="SMALL",
                scenario_code="MULTIBANK_SECONDARY",
                incorporated_on=date(2018, 1, 1),
                status="ACTIVE",
                rm_id=manager_id,
            )
        )
        session.add(
            MetricSnapshot(
                id=uuid4(),
                customer_id=customer_id,
                as_of_date=date(2026, 9, 30),
                window_days=90,
                calculation_version="test-flow-v1",
                values_json={"flow_visibility_opportunity": True},
                input_watermark="synthetic-test",
            )
        )
        session.add_all(
            [
                FlowVisibilityPolicy(
                    id=uuid4(),
                    policy_id="multibank-flow-visibility",
                    version=1,
                    active=True,
                    configuration_json={"domiciliationCooldownDays": 180},
                    justification="Politique active initiale",
                    created_by="migration-0020",
                ),
                FlowVisibilityPolicy(
                    id=uuid4(),
                    policy_id="multibank-flow-visibility",
                    version=2,
                    active=False,
                    configuration_json={"domiciliationCooldownDays": 120},
                    justification="Politique en attente de publication",
                    created_by="admin-01",
                ),
            ]
        )

    management = application_for("rule-management-service")
    management.state.session_factory = factory
    simulation = application_for("rule-simulation-service")
    simulation.state.session_factory = factory
    analyst_headers = {
        "X-Dev-Principal": json.dumps(
            {
                "subject": "analyst-01",
                "username": "analyste.metier",
                "roles": ["BUSINESS_ANALYST"],
            }
        )
    }
    approver_headers = {
        "X-Dev-Principal": json.dumps(
            {
                "subject": "approver-01",
                "username": "approbatrice.distincte",
                "roles": ["RULE_APPROVER"],
            }
        )
    }
    rule = {
        "ruleId": "FLOW_DOMICILIATION",
        "name": "Domiciliation des flux",
        "description": ("Règle commerciale synthétique; seuils HYPOTHÈSE À VALIDER AVEC BOA."),
        "scope": {"segment": ["SMALL", "MEDIUM"], "dataKind": "SYNTHETIC"},
        "conditions": [
            {
                "metric": "flow_visibility_opportunity",
                "operator": "=",
                "value": True,
                "unit": "BOOLEAN",
                "period": "90D",
            }
        ],
        "recommendation": {
            "opportunityType": "FLOW_DOMICILIATION",
            "products": ["BOA_PACK_BUSINESS_PME"],
            "horizon": "1-3_MONTHS",
        },
        "confidence": {
            "baseScore": 60,
            "weights": {"flow_visibility_opportunity": 25},
        },
        "lifecycle": {
            "validityDays": 90,
            "dismissedCooldownDays": 180,
            "convertedCooldownDays": 180,
            "deferredCooldownDays": 180,
            "expiredCooldownDays": 7,
        },
    }
    management_client = TestClient(management)
    simulation_client = TestClient(simulation)

    created = management_client.post("/internal/v1/rules", json=rule, headers=analyst_headers)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"
    validated = management_client.post(
        "/internal/v1/rules/FLOW_DOMICILIATION/validate",
        json={"reason": "Contrôle de définition"},
        headers=analyst_headers,
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["rule"]["status"] == "VALIDATED"
    simulated = simulation_client.post(
        "/internal/v1/rules/FLOW_DOMICILIATION/simulate",
        json={
            "period": {"from": "2026-09-01", "to": "2026-09-30"},
            "population": {"segment": "SME", "dataKind": "SYNTHETIC"},
        },
        headers=analyst_headers,
    )
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["rule"]["status"] == "SIMULATED"
    assert simulated.json()["populationAnalyzed"] == 1
    assert simulated.json()["matchedCustomers"] == 1
    assert simulated.json()["impact"]["populationAffected"] == 1
    submitted = management_client.post(
        "/internal/v1/rules/FLOW_DOMICILIATION/submit",
        json={"reason": "Soumission par l'analyste"},
        headers=analyst_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    self_approval = management_client.post(
        "/internal/v1/rules/FLOW_DOMICILIATION/approve",
        json={"reason": "Doit être refusé"},
        headers={
            "X-Dev-Principal": json.dumps(
                {
                    "subject": "analyst-01",
                    "username": "analyste.metier",
                    "roles": ["RULE_APPROVER"],
                }
            )
        },
    )
    assert self_approval.status_code == 403
    assert self_approval.json()["code"] == "SELF_APPROVAL_FORBIDDEN"
    approved = management_client.post(
        "/internal/v1/rules/FLOW_DOMICILIATION/approve",
        json={"reason": "Approbation distincte"},
        headers=approver_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    published = management_client.post(
        "/internal/v1/rules/FLOW_DOMICILIATION/publish",
        json={"reason": "Publication gouvernée"},
        headers=approver_headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "ACTIVE"
    assert published.json()["activeVersion"] == 1

    with factory() as session:
        actions = list(
            session.scalars(select(RuleAuditLog.action).order_by(RuleAuditLog.timestamp))
        )
        policies = list(
            session.scalars(select(FlowVisibilityPolicy).order_by(FlowVisibilityPolicy.version))
        )
    assert actions == [
        "CREATED",
        "VALIDATED",
        "SIMULATED",
        "SUBMITTED",
        "APPROVED",
        "PUBLISHED",
        "ACTIVATED",
    ]
    assert [policy.active for policy in policies] == [False, True]
