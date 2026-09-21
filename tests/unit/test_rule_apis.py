from __future__ import annotations

from boa_oi.api import application_for
from boa_oi.models import Base
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
