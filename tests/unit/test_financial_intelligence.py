from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from typing import Any

import pytest
from boa_oi.api import application_for
from boa_oi.financial_intelligence.authorization import FI_PURPOSE, authorize
from boa_oi.financial_intelligence.contracts import no_raw_financial_fields
from boa_oi.financial_intelligence.service import (
    FinancialIntelligenceComposer,
    OwnerClients,
    cash_position,
    flow_summary,
    opportunity_projection,
    signal_projection,
)
from boa_oi.financial_intelligence_models import (
    DataAccessGrant,
    ExternalConsumer,
    ExternalPortfolio,
    ExternalPortfolioCompany,
    FinancialIntelligenceAccessAudit,
)
from boa_oi.platform import Principal, Problem, current_principal, get_session
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
AS_OF = date(2026, 9, 20)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_schemas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS financial_intelligence")
        cursor.close()

    for table in (
        ExternalConsumer.__table__,
        ExternalPortfolio.__table__,
        ExternalPortfolioCompany.__table__,
        DataAccessGrant.__table__,
        FinancialIntelligenceAccessAudit.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        for suffix, company in (("A", "SME-00001"), ("B", "SME-00003")):
            consumer_id = deterministic_uuid("test-fi-consumer", suffix)
            portfolio_id = deterministic_uuid("test-fi-portfolio", suffix)
            session.add(
                ExternalConsumer(
                    id=consumer_id,
                    consumer_ref=f"CONSUMER-{suffix}",
                    display_name=f"Synthetic Consumer {suffix}",
                    consumer_type="FUND",
                    status="ACTIVE",
                    allowed_scopes=[
                        "financial.read",
                        "portfolio.read",
                        "signals.read",
                        "opportunities.read",
                    ],
                    synthetic_data=True,
                )
            )
            session.add(
                ExternalPortfolio(
                    id=portfolio_id,
                    consumer_id=consumer_id,
                    portfolio_ref=f"PORTFOLIO-FUND-00{1 if suffix == 'A' else 2}",
                    fund_ref=f"FUND-00{1 if suffix == 'A' else 2}",
                    display_name=f"Synthetic Fund {suffix}",
                    status="ACTIVE",
                )
            )
            session.add(
                ExternalPortfolioCompany(
                    id=deterministic_uuid("test-fi-membership", suffix),
                    portfolio_id=portfolio_id,
                    company_ref=company,
                    status="ACTIVE",
                    valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )
            )
            for scope in (
                "financial.read",
                "portfolio.read",
                "signals.read",
                "opportunities.read",
            ):
                session.add(
                    DataAccessGrant(
                        id=deterministic_uuid("test-fi-grant", suffix, scope),
                        grant_ref=f"TEST-{suffix}-{scope}",
                        consumer_id=consumer_id,
                        portfolio_id=portfolio_id,
                        subject_id=f"fund-{suffix.lower()}",
                        client_id="test-client",
                        scope=scope,
                        purpose=FI_PURPOSE,
                        status="ACTIVE",
                        valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        valid_until=datetime(2099, 1, 1, tzinfo=timezone.utc),
                        authorization_reference=f"AUTH-{suffix}-{scope}",
                    )
                )
        consumer_a = session.scalar(
            select(ExternalConsumer).where(ExternalConsumer.consumer_ref == "CONSUMER-A")
        )
        portfolio_a = session.scalar(
            select(ExternalPortfolio).where(ExternalPortfolio.fund_ref == "FUND-001")
        )
        assert consumer_a and portfolio_a
        for subject, status, valid_until, revoked_at in (
            ("fund-expired", "EXPIRED", datetime(2025, 1, 2, tzinfo=timezone.utc), None),
            ("fund-revoked", "REVOKED", datetime(2099, 1, 1, tzinfo=timezone.utc), NOW),
        ):
            session.add(
                DataAccessGrant(
                    id=deterministic_uuid("test-fi-grant", subject),
                    grant_ref=f"TEST-{subject}",
                    consumer_id=consumer_a.id,
                    portfolio_id=portfolio_a.id,
                    subject_id=subject,
                    client_id="test-client",
                    scope="financial.read",
                    purpose=FI_PURPOSE,
                    status=status,
                    valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    valid_until=valid_until,
                    revoked_at=revoked_at,
                    authorization_reference=f"AUTH-{subject}",
                )
            )
    return factory


def principal(subject: str, *scopes: str, role: str = "EXTERNAL_CONSUMER") -> Principal:
    return Principal(
        subject=subject,
        roles={role},
        scopes=set(scopes),
        client_id="test-client",
    )


def test_oidc_claims_preserve_explicit_fi_scopes_without_wildcard() -> None:
    from boa_oi.platform import _principal_from_claims

    parsed = _principal_from_claims(
        {
            "sub": "external-fund-a",
            "preferred_username": "fund.demo",
            "azp": "boa-sme-spa",
            "realm_access": {"roles": ["EXTERNAL_CONSUMER"]},
            "fi_scopes": ["financial.read", "portfolio.read"],
        }
    )
    assert parsed.client_id == "boa-sme-spa"
    assert parsed.roles == {"EXTERNAL_CONSUMER"}
    assert parsed.scopes == {"financial.read", "portfolio.read"}
    assert "*" not in parsed.scopes


def request_for(path: str = "/internal/v1/financial-intelligence/companies/SME-00001/summary"):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 123),
            "scheme": "http",
        }
    )


def test_authorization_denies_missing_scope_and_audits(session_factory) -> None:
    with session_factory() as session:
        request = request_for()
        request.state.correlation_id = "trace-scope"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a"),
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=NOW,
            )
        assert exc_info.value.status_code == 403
        audit = session.scalar(
            select(FinancialIntelligenceAccessAudit).where(
                FinancialIntelligenceAccessAudit.trace_id == "trace-scope"
            )
        )
        assert audit and audit.result == "DENY" and audit.reason_code == "SCOPE_MISSING"
        assert "token" not in (audit.safe_details or "").lower()


@pytest.mark.parametrize("subject", ["fund-expired", "fund-revoked"])
def test_authorization_denies_expired_and_revoked_grants_with_404(
    session_factory, subject: str
) -> None:
    with session_factory() as session:
        request = request_for()
        request.state.correlation_id = f"trace-{subject}"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal(subject, "financial.read"),
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=NOW,
            )
        assert exc_info.value.status_code == 404


def test_fund_a_cannot_tamper_company_url_or_portfolio_id(session_factory) -> None:
    with session_factory() as session:
        request = request_for("/companies/SME-00003/summary")
        request.state.correlation_id = "trace-company-tamper"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a", "financial.read"),
                required_scopes=("financial.read",),
                company_ref="SME-00003",
                now=NOW,
            )
        assert exc_info.value.status_code == 404
        request = request_for("/portfolios/PORTFOLIO-FUND-002/summary")
        request.state.correlation_id = "trace-portfolio-tamper"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a", "financial.read", "portfolio.read"),
                required_scopes=("financial.read", "portfolio.read"),
                portfolio_ref="PORTFOLIO-FUND-002",
                now=NOW,
            )
        assert exc_info.value.status_code == 404


def test_authorization_resolves_consumer_from_subject_and_audits_allow(session_factory) -> None:
    with session_factory() as session:
        request = request_for()
        request.state.correlation_id = "trace-allow"
        context = authorize(
            session,
            request=request,
            principal=principal("fund-a", "financial.read"),
            required_scopes=("financial.read",),
            company_ref="SME-00001",
            now=NOW,
        )
        assert context.consumer_ref == "CONSUMER-A"
        assert context.fund_ref == "FUND-001"
        assert context.portfolio_ref == "PORTFOLIO-FUND-001"
        audit = session.scalar(
            select(FinancialIntelligenceAccessAudit).where(
                FinancialIntelligenceAccessAudit.trace_id == "trace-allow"
            )
        )
        assert audit and audit.result == "ALLOW"
        assert audit.authorization_reference == "AUTH-A-financial.read"


def test_company_membership_is_evaluated_at_as_of_not_authorization_time(
    session_factory,
) -> None:
    with session_factory() as session:
        membership = session.scalar(
            select(ExternalPortfolioCompany).where(
                ExternalPortfolioCompany.company_ref == "SME-00001"
            )
        )
        assert membership is not None
        membership.valid_from = datetime(2026, 10, 1, tzinfo=timezone.utc)
        request = request_for()
        request.state.correlation_id = "trace-membership-before-start"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a", "financial.read"),
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=datetime(2026, 10, 2, tzinfo=timezone.utc),
                membership_at=datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc),
            )
        assert exc_info.value.status_code == 404

        membership.valid_from = datetime(2025, 1, 1, tzinfo=timezone.utc)
        membership.valid_until = datetime(2026, 9, 21, tzinfo=timezone.utc)
        membership.status = "INACTIVE"
        request.state.correlation_id = "trace-membership-historical"
        context = authorize(
            session,
            request=request,
            principal=principal("fund-a", "financial.read"),
            required_scopes=("financial.read",),
            company_ref="SME-00001",
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
            membership_at=datetime(2026, 9, 20, 23, 59, tzinfo=timezone.utc),
        )
        assert context.portfolio_ref == "PORTFOLIO-FUND-001"

        request.state.correlation_id = "trace-membership-after-end"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a", "financial.read"),
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=datetime(2026, 10, 2, tzinfo=timezone.utc),
                membership_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
            )
        assert exc_info.value.status_code == 404


def test_inconsistent_consumer_portfolio_grant_never_authorizes(session_factory) -> None:
    with session_factory.begin() as session:
        consumer_a = session.scalar(
            select(ExternalConsumer).where(ExternalConsumer.consumer_ref == "CONSUMER-A")
        )
        portfolio_b = session.scalar(
            select(ExternalPortfolio).where(ExternalPortfolio.fund_ref == "FUND-002")
        )
        assert consumer_a is not None and portfolio_b is not None
        session.add(
            DataAccessGrant(
                id=deterministic_uuid("test-fi-grant", "cross-consumer"),
                grant_ref="TEST-CROSS-CONSUMER",
                consumer_id=consumer_a.id,
                portfolio_id=portfolio_b.id,
                subject_id="fund-cross",
                client_id="test-client",
                scope="financial.read",
                purpose=FI_PURPOSE,
                status="ACTIVE",
                valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2099, 1, 1, tzinfo=timezone.utc),
                authorization_reference="AUTH-CROSS-CONSUMER",
            )
        )

    with session_factory() as session:
        request = request_for("/companies/SME-00003/summary")
        request.state.correlation_id = "trace-cross-consumer-grant"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-cross", "financial.read"),
                required_scopes=("financial.read",),
                company_ref="SME-00003",
                now=NOW,
                membership_at=NOW,
            )
        assert exc_info.value.status_code == 404


def test_authorization_denies_wrong_oidc_client_and_consumer_scope(session_factory) -> None:
    with session_factory() as session:
        request = request_for()
        request.state.correlation_id = "trace-client"
        wrong_client = principal("fund-a", "financial.read")
        wrong_client.client_id = "untrusted-client"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=wrong_client,
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=NOW,
            )
        assert exc_info.value.status_code == 404

        consumer = session.scalar(
            select(ExternalConsumer).where(ExternalConsumer.consumer_ref == "CONSUMER-A")
        )
        assert consumer is not None
        consumer.allowed_scopes = ["portfolio.read"]
        session.flush()
        request.state.correlation_id = "trace-consumer-scope"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a", "financial.read"),
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=NOW,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "FI_SCOPE_MISSING"


@pytest.mark.parametrize("role", ["ADMIN", "SERVICE"])
def test_authorization_rejects_non_external_roles(session_factory, role: str) -> None:
    with session_factory() as session:
        request = request_for()
        request.state.correlation_id = f"trace-role-{role.lower()}"
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=principal("fund-a", "financial.read", role=role),
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=NOW,
            )
        assert exc_info.value.status_code == 403


def test_authorization_requires_explicit_client_binding(session_factory) -> None:
    with session_factory() as session:
        request = request_for()
        request.state.correlation_id = "trace-client-missing"
        unbound = principal("fund-a", "financial.read")
        unbound.client_id = None
        with pytest.raises(Problem) as exc_info:
            authorize(
                session,
                request=request,
                principal=unbound,
                required_scopes=("financial.read",),
                company_ref="SME-00001",
                now=NOW,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "FI_CLIENT_BINDING_REQUIRED"


@pytest.mark.parametrize(
    ("field", "value"),
    [("client_id", None), ("purpose", "ANOTHER_PURPOSE")],
)
def test_grant_schema_rejects_missing_client_or_wrong_purpose(
    session_factory, field: str, value: str | None
) -> None:
    with session_factory() as session:
        grant = session.scalar(
            select(DataAccessGrant).where(DataAccessGrant.subject_id == "fund-a")
        )
        assert grant is not None
        setattr(grant, field, value)
        with pytest.raises(IntegrityError):
            session.flush()


def test_point_in_time_projection_and_calculations() -> None:
    signals = signal_projection(
        {
            "data": [
                {
                    "signalId": "SIG-1",
                    "type": "INFLOW_GROWTH",
                    "severity": "HIGH",
                    "value": 0.2,
                    "threshold": 0.1,
                    "detectedAt": "2026-09-20T10:00:00Z",
                    "status": "ACTIVE",
                    "metricReferences": ["inflow_amount"],
                    "ruleVersion": "1",
                },
                {
                    "signalId": "SIG-FUTURE",
                    "type": "FUTURE",
                    "severity": "LOW",
                    "value": 1,
                    "threshold": 1,
                    "detectedAt": "2026-09-21T00:00:00Z",
                    "status": "ACTIVE",
                },
            ]
        },
        as_of=AS_OF,
    )
    opportunities = opportunity_projection(
        {
            "data": [
                {
                    "opportunityId": "OPP-1",
                    "opportunityType": "CASH_INVESTMENT",
                    "status": "OPEN",
                    "confidence": 0.8,
                    "generatedAt": "2026-09-20T08:00:00Z",
                    "ruleVersion": "1",
                    "engineVersion": "rules-v1",
                },
                {
                    "opportunityId": "OPP-FUTURE",
                    "opportunityType": "FUTURE",
                    "status": "OPEN",
                    "confidence": 0.9,
                    "generatedAt": "2026-09-21T08:00:00Z",
                },
            ]
        },
        as_of=AS_OF,
    )
    metrics = {
        "inflow_amount": {"currentValue": 120.0, "growthRate": 0.2},
        "outflow_amount": {"currentValue": 80.0, "growthRate": -0.1},
        "transaction_count": {"currentValue": 12, "growthRate": 0.5},
        "average_balance": {"currentValue": 70.0, "growthRate": 0.1},
        "minimum_balance": {"currentValue": 20.0},
        "maximum_balance": {"currentValue": 140.0},
    }
    assert [item.signalRef for item in signals] == ["SIG-1"]
    assert [item.opportunityId for item in opportunities] == ["OPP-1"]
    assert signals[0].status is None
    assert signals[0].stateAsOfStatus == "NOT_IMPLEMENTED"
    assert opportunities[0].status is None
    assert opportunities[0].stateAsOfStatus == "NOT_IMPLEMENTED"
    assert flow_summary(metrics).model_dump() == {
        "currency": "MAD",
        "period": "90D",
        "inflows": 120.0,
        "outflows": 80.0,
        "netFlow": 40.0,
        "inflowTrend": 0.2,
        "outflowTrend": -0.1,
        "netFlowRatio": 0.5,
        "transactionCount": 12,
        "activityTrend": 0.5,
        "concentrationRatio": None,
        "volatility": None,
    }
    assert cash_position(metrics).averageBalance == 70.0


class FakeOwners:
    async def get(self, owner: str, path: str, **kwargs: Any) -> Any:
        del path, kwargs
        if owner == "customer":
            return {
                "customerId": "SME-00001",
                "legalName": "Synthetic SME 1",
                "sector": "BTP",
                "segment": "SMALL",
                "status": "ACTIVE",
                "flowVisibility": {
                    "level": "PARTIAL",
                    "estimatedShare": 0.5,
                    "method": "DECLARED_TURNOVER",
                    "categorizationCoverage": 0.9,
                    "fingerprintCount90d": 2,
                    "asOf": AS_OF.isoformat(),
                },
            }
        if owner == "analytics":
            return {
                "data": [
                    {
                        "metric": metric,
                        "currentValue": value,
                        "previousPeriodValue": None,
                        "growthRate": growth,
                        "period": "90D",
                        "asOf": AS_OF.isoformat(),
                        "calculationVersion": "analytics-0.1.0",
                        "dataQuality": "VALID",
                        "dataCoverage": 1.0,
                        "sampleSize": 90,
                    }
                    for metric, value, growth in (
                        ("inflow_amount", 120.0, 0.2),
                        ("outflow_amount", 80.0, -0.1),
                        ("transaction_count", 12.0, 0.5),
                        ("average_balance", 70.0, 0.1),
                    )
                ]
            }
        if owner == "signal":
            return {
                "data": [
                    {
                        "signalId": "SIG-1",
                        "type": "INFLOW_GROWTH",
                        "severity": "HIGH",
                        "value": 0.2,
                        "threshold": 0.1,
                        "detectedAt": "2026-09-20T10:00:00Z",
                        "status": "ACTIVE",
                        "metricReferences": ["inflow_amount"],
                        "ruleVersion": "1",
                    }
                ]
            }
        if owner == "opportunity":
            return {
                "data": [
                    {
                        "opportunityId": "OPP-1",
                        "opportunityType": "CASH_INVESTMENT",
                        "status": "OPEN",
                        "confidence": 0.8,
                        "generatedAt": "2026-09-20T08:00:00Z",
                        "ruleVersion": "1",
                        "engineVersion": "rules-v1",
                    }
                ]
            }
        return {
            "model": {
                "featureSetVersion": "features-v1",
                "modelVersion": "shadow-v1",
                "trainingDatasetVersion": "dataset-v1",
            },
            "combination": {
                "method": "RULES_ONLY",
                "mlObservationMode": "POC_SHADOW",
                "rulesWeight": 1,
                "mlWeight": 0,
            },
        }


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    application_for("financial-intelligence-service").dependency_overrides.clear()
    application_for("api-gateway").dependency_overrides.clear()


def test_internal_api_payload_minimization_and_ml_invariants(session_factory, monkeypatch) -> None:
    from boa_oi import financial_intelligence_api

    monkeypatch.setattr(
        financial_intelligence_api,
        "composer",
        FinancialIntelligenceComposer(FakeOwners()),
    )
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal("fund-a", "financial.read")
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/companies/SME-00001/summary",
        params={"asOf": AS_OF.isoformat()},
        headers={"X-Correlation-ID": "trace-api"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["executionMode"] == "DETERMINISTIC_RULES"
    assert payload["meta"]["mlGovernanceStatus"] == "VERIFIED"
    assert payload["meta"]["mlMode"] == "POC_SHADOW"
    assert payload["meta"]["rulesWeight"] == 1.0
    assert payload["meta"]["mlWeight"] == 0.0
    assert payload["meta"]["syntheticData"] is True
    assert payload["meta"]["nonProduction"] is True
    assert payload["meta"]["requestId"] == "trace-api"
    assert payload["meta"]["partial"] is False
    assert payload["meta"]["featureVersion"] == "features-v1"
    assert payload["meta"]["modelVersion"] == "shadow-v1"
    assert payload["meta"]["trainingDatasetVersion"] == "dataset-v1"
    assert payload["data"]["companyId"] == "SME-00001"
    assert no_raw_financial_fields(payload)
    serialized = json.dumps(payload).lower()
    assert (
        "iban" not in serialized
        and "remittance" not in serialized
        and "counterparty" not in serialized
    )
    rejected = TestClient(app).get(
        "/internal/v1/financial-intelligence/companies/SME-00001/summary",
        params={"asOf": AS_OF.isoformat(), "consumerId": "CONSUMER-B"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "UNKNOWN_FILTER"


def test_internal_api_marks_partial_when_an_owner_is_unavailable(
    session_factory, monkeypatch
) -> None:
    from boa_oi import financial_intelligence_api

    class PartialOwners(FakeOwners):
        async def get(self, owner: str, path: str, **kwargs: Any) -> Any:
            if owner == "analytics":
                raise Problem(503, "ANALYTICS_UNAVAILABLE", "Synthetic dependency outage.")
            return await super().get(owner, path, **kwargs)

    monkeypatch.setattr(
        financial_intelligence_api,
        "composer",
        FinancialIntelligenceComposer(PartialOwners()),
    )
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal("fund-a", "financial.read")
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/companies/SME-00001/summary",
        params={"asOf": AS_OF.isoformat()},
        headers={"X-Correlation-ID": "trace-partial"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["partial"] is True
    assert {
        (item["source"], item["capability"], item["status"], item.get("reason"))
        for item in payload["meta"]["sourceStatus"]
    } >= {
        (
            "analytics-service",
            "booked-point-in-time-metrics",
            "UNAVAILABLE",
            "ANALYTICS_UNAVAILABLE",
        )
    }
    assert payload["data"]["cashPosition"]["averageBalance"] is None


def test_gateway_routes_and_direct_api_require_valid_principal(
    session_factory, monkeypatch
) -> None:
    from boa_oi import gateway_api

    fi_paths = set(application_for("financial-intelligence-service").openapi()["paths"])
    assert "/internal/v1/financial-intelligence/portfolios" in fi_paths
    assert "/internal/v1/financial-intelligence/companies/{company_id}/flow-summary" in fi_paths
    public_paths = set(application_for("api-gateway").openapi()["paths"])
    assert "/api/v1/financial-intelligence/portfolios" in public_paths
    assert "/api/v1/financial-intelligence/portfolios/{portfolio_id}/summary" in public_paths
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal(
        "fund-a", "financial.read", role="RELATIONSHIP_MANAGER"
    )
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/companies/SME-00001/summary",
        params={"asOf": AS_OF.isoformat()},
    )
    assert response.status_code == 403

    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, **kwargs: Any) -> Any:
        captured.update(method=method, url=url, **kwargs)
        return {"data": {}, "meta": {}}

    monkeypatch.setattr(gateway_api, "service_request", fake_request)
    monkeypatch.setenv("FINANCIAL_INTELLIGENCE_SERVICE_URL", "http://fi:8080")
    gateway = application_for("api-gateway")
    gateway.dependency_overrides[current_principal] = lambda: principal(
        "fund-a", "financial.read", role="EXTERNAL_CONSUMER"
    )
    response = TestClient(gateway).get(
        "/api/v1/financial-intelligence/companies/SME-00001/summary",
        params={"asOf": AS_OF.isoformat()},
        headers={"Authorization": "Bearer opaque-do-not-log"},
    )
    assert response.status_code == 200
    assert captured["url"] == (
        "http://fi:8080/internal/v1/financial-intelligence/companies/SME-00001/summary"
    )
    assert captured["timeout"] == 600.0
    assert captured["params"] == {"asOf": AS_OF.isoformat()}
    assert captured["incoming_authorization"] == "Bearer opaque-do-not-log"

    response = TestClient(gateway).get(
        "/api/v1/financial-intelligence/portfolios",
        params={"asOf": AS_OF.isoformat(), "pageSize": 1, "offset": 1},
        headers={"Authorization": "Bearer opaque-do-not-log"},
    )
    assert response.status_code == 200
    assert captured["params"] == {"asOf": AS_OF.isoformat(), "pageSize": "1", "offset": "1"}


def test_portfolio_catalog_is_backend_authorized(session_factory) -> None:
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal(
        "fund-a", "financial.read", "portfolio.read"
    )
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/portfolios",
        params={"asOf": AS_OF.isoformat()},
        headers={"X-Correlation-ID": "trace-catalog"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] == {
        "totalCount": 1,
        "pageSize": 50,
        "nextOffset": None,
        "portfolios": [
            {
                "portfolioId": "PORTFOLIO-FUND-001",
                "fundId": "FUND-001",
                "name": "Synthetic Fund A",
                "companyCount": 1,
            }
        ],
    }
    assert payload["meta"]["traceId"] == "trace-catalog"
    second_page = TestClient(app).get(
        "/internal/v1/financial-intelligence/portfolios",
        params={"asOf": AS_OF.isoformat(), "pageSize": 1, "offset": 1},
    )
    assert second_page.status_code == 200
    assert second_page.json()["data"] == {
        "totalCount": 1,
        "pageSize": 1,
        "nextOffset": None,
        "portfolios": [],
    }


def test_portfolio_catalog_counts_inactive_membership_before_its_end(
    session_factory,
) -> None:
    with session_factory.begin() as session:
        membership = session.scalar(
            select(ExternalPortfolioCompany).where(
                ExternalPortfolioCompany.company_ref == "SME-00001"
            )
        )
        assert membership is not None
        membership.status = "INACTIVE"
        membership.valid_until = datetime(2026, 10, 1, tzinfo=timezone.utc)

    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal(
        "fund-a", "financial.read", "portfolio.read"
    )
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/portfolios",
        params={"asOf": AS_OF.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["data"]["portfolios"][0]["companyCount"] == 1


def test_portfolio_summary_excludes_future_membership(session_factory, monkeypatch) -> None:
    from boa_oi import financial_intelligence_api

    with session_factory.begin() as session:
        membership = session.scalar(
            select(ExternalPortfolioCompany).where(
                ExternalPortfolioCompany.company_ref == "SME-00001"
            )
        )
        assert membership is not None
        membership.valid_from = datetime(2026, 10, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(
        financial_intelligence_api,
        "composer",
        FinancialIntelligenceComposer(FakeOwners()),
    )
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal(
        "fund-a", "financial.read", "portfolio.read"
    )
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-001/summary",
        params={"asOf": AS_OF.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["data"]["companyCount"] == 0


def test_portfolio_summary_includes_inactive_membership_before_its_end(
    session_factory, monkeypatch
) -> None:
    from boa_oi import financial_intelligence_api

    with session_factory.begin() as session:
        membership = session.scalar(
            select(ExternalPortfolioCompany).where(
                ExternalPortfolioCompany.company_ref == "SME-00001"
            )
        )
        assert membership is not None
        membership.status = "INACTIVE"
        membership.valid_until = datetime(2026, 10, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(
        financial_intelligence_api,
        "composer",
        FinancialIntelligenceComposer(FakeOwners()),
    )
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal(
        "fund-a", "financial.read", "portfolio.read"
    )
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/portfolios/PORTFOLIO-FUND-001/summary",
        params={"asOf": AS_OF.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["data"]["companyCount"] == 1


def test_owner_clients_never_forward_external_bearer(monkeypatch) -> None:
    from boa_oi.financial_intelligence import service

    captured: dict[str, Any] = {}

    async def fake_service_request(method: str, url: str, **kwargs: Any) -> Any:
        captured.update(method=method, url=url, **kwargs)
        return {"ok": True}

    monkeypatch.setattr(service, "service_request", fake_service_request)
    monkeypatch.setenv("CUSTOMER_SERVICE_URL", "http://customer:8080")
    result = asyncio.run(
        OwnerClients().get("customer", "customers/SME-00001", trace_id="trace-owner")
    )
    assert result == {"ok": True}
    assert "incoming_authorization" not in captured
    assert "dev_principal" not in captured


@pytest.mark.parametrize(
    "combination",
    [
        {
            "method": "HYBRID_ML",
            "mlObservationMode": "ACTIVE",
            "rulesWeight": 0.5,
            "mlWeight": 0.5,
        },
        {
            "method": "RULES_ONLY",
            "mlObservationMode": "ACTIVE",
            "rulesWeight": 1,
            "mlWeight": 0,
        },
    ],
)
def test_composer_rejects_ml_influence_or_non_shadow_mode(
    combination: dict[str, Any],
) -> None:
    class InvalidPortfolio(FakeOwners):
        async def get(self, owner: str, path: str, **kwargs: Any) -> Any:
            if owner == "portfolio":
                return {"combination": combination}
            return await super().get(owner, path, **kwargs)

    async def execute() -> None:
        await FinancialIntelligenceComposer(InvalidPortfolio()).company_summary(
            "SME-00001",
            portfolio_id="PORTFOLIO-FUND-001",
            fund_id="FUND-001",
            as_of=AS_OF,
            trace_id="trace-invalid-ml",
        )

    with pytest.raises(Problem) as exc_info:
        asyncio.run(execute())
    assert exc_info.value.code == "DEPENDENCY_INVALID_RESPONSE"


def test_composer_propagates_as_of_to_propensity_owner() -> None:
    class CapturingOwners(FakeOwners):
        portfolio_params: dict[str, Any] | None = None

        async def get(self, owner: str, path: str, **kwargs: Any) -> Any:
            if owner == "portfolio":
                self.portfolio_params = kwargs.get("params")
            return await super().get(owner, path, **kwargs)

    owners = CapturingOwners()
    asyncio.run(
        FinancialIntelligenceComposer(owners).company_summary(
            "SME-00001",
            portfolio_id="PORTFOLIO-FUND-001",
            fund_id="FUND-001",
            as_of=AS_OF,
            trace_id="trace-propensity-as-of",
        )
    )
    assert owners.portfolio_params == {"asOf": AS_OF.isoformat()}


def test_missing_portfolio_governance_is_not_attested(session_factory, monkeypatch) -> None:
    from boa_oi import financial_intelligence_api

    class MissingPortfolio(FakeOwners):
        async def get(self, owner: str, path: str, **kwargs: Any) -> Any:
            if owner == "portfolio":
                raise Problem(503, "PORTFOLIO_UNAVAILABLE", "Synthetic dependency outage.")
            return await super().get(owner, path, **kwargs)

    monkeypatch.setattr(
        financial_intelligence_api,
        "composer",
        FinancialIntelligenceComposer(MissingPortfolio()),
    )
    app = application_for("financial-intelligence-service")
    app.dependency_overrides[get_session] = lambda: session_factory()
    app.dependency_overrides[current_principal] = lambda: principal("fund-a", "financial.read")
    response = TestClient(app).get(
        "/internal/v1/financial-intelligence/companies/SME-00001/summary",
        params={"asOf": AS_OF.isoformat()},
    )
    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["mlGovernanceStatus"] == "UNAVAILABLE"
    assert meta["deploymentMode"] is None
    assert meta["mlMode"] is None
    assert meta["rulesWeight"] is None
    assert meta["mlWeight"] is None
