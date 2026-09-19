"""Tests des ajouts backend au service de l'expérience UI premium :
persona de développement, registre ML, série d'activité, agrégats agence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from boa_oi.api import application_for
from boa_oi.platform import Principal, _dev_principal
from boa_oi.portfolio_api import _branch_breakdowns, _counter_payload
from boa_oi.technical.reference import branch_label
from fastapi.testclient import TestClient


def test_dev_principal_is_parsed_only_from_valid_json():
    persona = _dev_principal(
        json.dumps(
            {
                "subject": "rm-01",
                "username": "ahmed.mansouri",
                "roles": ["relationship_manager"],
                "relationshipManagerIds": ["rm-01"],
                "branchIds": "BR-01",
            }
        )
    )
    assert isinstance(persona, Principal)
    assert persona.roles == {"RELATIONSHIP_MANAGER"}
    assert persona.relationship_manager_ids == ("rm-01",)
    assert persona.branch_ids == ("BR-01",)
    assert _dev_principal(None) is None
    with pytest.raises(Exception, match="valid JSON"):
        _dev_principal("{not json")
    with pytest.raises(Exception, match="subject"):
        _dev_principal(json.dumps({"roles": ["ADMIN"]}))


def test_dev_principal_header_is_ignored_when_auth_is_enabled(monkeypatch):
    monkeypatch.delenv("BOA_AUTH_DISABLED", raising=False)
    client = TestClient(application_for("customer-service"), raise_server_exceptions=False)
    response = client.get(
        "/internal/v1/customers",
        headers={"X-Dev-Principal": json.dumps({"subject": "rm-01", "roles": ["ADMIN"]})},
    )
    assert response.status_code == 401


def test_gateway_exposes_activity_and_model_registry_routes(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    spec = TestClient(application_for("api-gateway")).get("/openapi.json").json()
    paths = set(spec["paths"])
    assert "/api/v1/customers/{customer_id}/activity" in paths
    assert "/api/v1/ml/models" in paths
    assert "/api/v1/ml/models/active" in paths
    assert "/api/v1/ml/models/{model_version}" in paths


def test_activity_endpoint_rejects_unknown_filters_and_bad_granularity(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    client = TestClient(application_for("transaction-service"), raise_server_exceptions=False)
    response = client.get("/internal/v1/customers/SME-00001/activity?foo=1")
    assert response.status_code in {400, 503}
    if response.status_code == 400:
        assert response.json()["code"] == "UNKNOWN_FILTER"
    response = client.get("/internal/v1/customers/SME-00001/activity?granularity=YEAR")
    assert response.status_code in {422, 503}


def test_branch_labels_fallback_to_code():
    assert branch_label("BR-01") == "Casablanca Anfa"
    assert branch_label("BR-99") == "BR-99"
    assert branch_label(None) is None


class _Customer:
    def __init__(self, ref: str, sector: str) -> None:
        self.id = uuid4()
        self.customer_ref = ref
        self.sector_code = sector


class _Manager:
    def __init__(self, subject_id: str, name: str) -> None:
        self.subject_id = subject_id
        self.display_name = name


class _Opportunity:
    def __init__(self, customer_id, opp_type: str, priority: str, products: list[dict]) -> None:
        self.customer_id = customer_id
        self.opportunity_type = opp_type
        self.priority_level = priority
        self.generated_at = datetime(2026, 9, 30, tzinfo=timezone.utc)
        self.recommended_products_json = products
        self.priority_score = Decimal("80")
        self.confidence_score = Decimal("0.8")
        self.horizon = "1-3_MONTHS"
        self.status = "OPEN"


class _Action:
    def __init__(self, action_type: str, outcome: str | None) -> None:
        self.action_type = action_type
        self.outcome_type = outcome
        self.created_at = datetime(2026, 9, 18, tzinfo=timezone.utc)


def test_branch_breakdowns_aggregate_real_rows(monkeypatch):
    alpha = _Customer("SME-00001", "INDUSTRIE")
    beta = _Customer("SME-00002", "BTP")
    manager = _Manager("rm-01", "Ahmed Mansouri")
    rows = [(alpha, manager), (beta, manager)]
    opportunities = {
        alpha.id: [
            _Opportunity(alpha.id, "INVESTMENT_FINANCING", "P1", [{"name": "Investment Financing"}])
        ],
        beta.id: [
            _Opportunity(beta.id, "TRADE_FINANCE", "P2", [{"name": "Trade Finance"}]),
            _Opportunity(beta.id, "INVESTMENT_FINANCING", "P1", []),
        ],
    }
    monkeypatch.setattr("boa_oi.portfolio_api._opportunities", lambda _s, _ids: opportunities)
    payload = _branch_breakdowns(
        None,
        rows,
        [_Action("CONTACT_CUSTOMER", "CONTACTED"), _Action("DISMISS_OPPORTUNITY", "NOT_RELEVANT")],
    )
    by_type = {item["opportunityType"]: item["count"] for item in payload["opportunitiesByType"]}
    assert by_type == {"INVESTMENT_FINANCING": 2, "TRADE_FINANCE": 1}
    assert payload["opportunitiesBySector"][0] == {
        "sector": "BTP",
        "count": 2,
        "share": pytest.approx(2 / 3),
    }
    assert (
        payload["opportunitiesByRelationshipManager"][0]["relationshipManagerName"]
        == "Ahmed Mansouri"
    )
    assert payload["opportunityTimeline"] == [{"date": "2026-09-30", "count": 3}]
    assert {item["outcome"] for item in payload["outcomes"]} == {"CONTACTED", "NOT_RELEVANT"}
    assert _counter_payload({}, "x") == []
