from __future__ import annotations

from datetime import datetime, timezone

from boa_oi.financial_intelligence_models import (
    DataAccessGrant,
    ExternalConsumer,
    ExternalPortfolio,
    ExternalPortfolioCompany,
)
from boa_oi.models.entities import Customer
from boa_oi.technical.ids import deterministic_uuid
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

FI_SEED_VERSION = "financial-intelligence-synthetic-v1"
VALID_FROM = datetime(2025, 1, 1, tzinfo=timezone.utc)
VALID_UNTIL = datetime(2099, 1, 1, tzinfo=timezone.utc)
EXPIRED_AT = datetime(2025, 6, 30, tzinfo=timezone.utc)
REVOKED_AT = datetime(2026, 1, 15, tzinfo=timezone.utc)

CONSUMERS = (
    ("CONSUMER-A", "Synthetic External Consumer A", "FUND", "external-fund-a"),
    ("CONSUMER-B", "Synthetic External Consumer B", "FUND", "external-fund-b"),
)
PORTFOLIOS = (
    ("PORTFOLIO-FUND-001", "FUND-001", "Synthetic Fund A", "CONSUMER-A"),
    ("PORTFOLIO-FUND-002", "FUND-002", "Synthetic Fund B", "CONSUMER-B"),
    ("PORTFOLIO-PERF-010", "FUND-PERF-010", "Synthetic Performance 10", "CONSUMER-A"),
    ("PORTFOLIO-PERF-050", "FUND-PERF-050", "Synthetic Performance 50", "CONSUMER-A"),
    ("PORTFOLIO-PERF-100", "FUND-PERF-100", "Synthetic Performance 100", "CONSUMER-A"),
    ("PORTFOLIO-PERF-500", "FUND-PERF-500", "Synthetic Performance 500", "CONSUMER-A"),
)
DEMO_MEMBERSHIPS = (
    ("PORTFOLIO-FUND-001", "SME-00001"),
    ("PORTFOLIO-FUND-001", "SME-00002"),
    ("PORTFOLIO-FUND-002", "SME-00003"),
    ("PORTFOLIO-FUND-002", "SME-00004"),
)
PERFORMANCE_SIZES = {
    "PORTFOLIO-PERF-010": 10,
    "PORTFOLIO-PERF-050": 50,
    "PORTFOLIO-PERF-100": 100,
    "PORTFOLIO-PERF-500": 500,
}
MEMBERSHIPS = DEMO_MEMBERSHIPS + tuple(
    (portfolio_ref, f"SME-{index:05d}")
    for portfolio_ref, size in PERFORMANCE_SIZES.items()
    for index in range(1, size + 1)
)
SUBJECTS = {
    "valid_a": "external-fund-a",
    "valid_b": "external-fund-b",
    "expired": "external-expired",
    "revoked": "external-revoked",
}
SCOPES = ("financial.read", "signals.read", "opportunities.read", "portfolio.read")


def seed_financial_intelligence(session: Session) -> dict[str, int | str]:
    expected_companies = {company for _portfolio, company in MEMBERSHIPS}
    existing_companies = set(
        session.scalars(
            select(Customer.customer_ref).where(Customer.customer_ref.in_(expected_companies))
        )
    )
    missing = sorted(expected_companies - existing_companies)
    if missing:
        raise RuntimeError(
            "FI seed requires existing synthetic companies from the owner Customer service: "
            + ", ".join(missing)
        )

    consumer_ids = {
        ref: deterministic_uuid("fi-consumer", FI_SEED_VERSION, ref)
        for ref, _name, _consumer_type, _subject in CONSUMERS
    }
    portfolio_ids = {
        ref: deterministic_uuid("fi-portfolio", FI_SEED_VERSION, ref)
        for ref, _fund, _name, _consumer in PORTFOLIOS
    }
    for consumer_ref, display_name, consumer_type, _subject in CONSUMERS:
        session.execute(
            pg_insert(ExternalConsumer)
            .values(
                id=consumer_ids[consumer_ref],
                consumer_ref=consumer_ref,
                display_name=display_name,
                consumer_type=consumer_type,
                status="ACTIVE",
                allowed_scopes=list(SCOPES),
                synthetic_data=True,
            )
            .on_conflict_do_nothing(index_elements=[ExternalConsumer.consumer_ref])
        )
    for portfolio_ref, fund_ref, display_name, consumer_ref in PORTFOLIOS:
        session.execute(
            pg_insert(ExternalPortfolio)
            .values(
                id=portfolio_ids[portfolio_ref],
                consumer_id=consumer_ids[consumer_ref],
                portfolio_ref=portfolio_ref,
                fund_ref=fund_ref,
                display_name=display_name,
                status="ACTIVE",
            )
            .on_conflict_do_nothing(index_elements=[ExternalPortfolio.fund_ref])
        )
    for portfolio_ref, company_ref in MEMBERSHIPS:
        session.execute(
            pg_insert(ExternalPortfolioCompany)
            .values(
                id=deterministic_uuid("fi-membership", FI_SEED_VERSION, portfolio_ref, company_ref),
                portfolio_id=portfolio_ids[portfolio_ref],
                company_ref=company_ref,
                status="ACTIVE",
                valid_from=VALID_FROM,
                valid_until=None,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ExternalPortfolioCompany.portfolio_id,
                    ExternalPortfolioCompany.company_ref,
                ]
            )
        )

    grant_specs: list[tuple[str, str, str, str, datetime, str, datetime | None]] = []
    for portfolio_ref, _fund_ref, _display_name, consumer_ref in PORTFOLIOS:
        suffix = "a" if consumer_ref == "CONSUMER-A" else "b"
        for scope in SCOPES:
            grant_specs.append(
                (
                    (f"GRANT-{suffix.upper()}-{portfolio_ref}-{scope.upper().replace('.', '-')}"),
                    SUBJECTS[f"valid_{suffix}"],
                    portfolio_ref,
                    scope,
                    VALID_UNTIL,
                    "ACTIVE",
                    None,
                )
            )
    grant_specs.extend(
        [
            (
                "GRANT-EXPIRED-FINANCIAL",
                SUBJECTS["expired"],
                "PORTFOLIO-FUND-001",
                "financial.read",
                EXPIRED_AT,
                "EXPIRED",
                None,
            ),
            (
                "GRANT-REVOKED-FINANCIAL",
                SUBJECTS["revoked"],
                "PORTFOLIO-FUND-002",
                "financial.read",
                VALID_UNTIL,
                "REVOKED",
                REVOKED_AT,
            ),
        ]
    )
    consumer_by_portfolio = {row[0]: row[3] for row in PORTFOLIOS}
    for grant_ref, subject_id, portfolio_ref, scope, valid_until, status, revoked_at in grant_specs:
        consumer_ref = consumer_by_portfolio[portfolio_ref]
        session.execute(
            pg_insert(DataAccessGrant)
            .values(
                id=deterministic_uuid("fi-grant", FI_SEED_VERSION, grant_ref),
                grant_ref=grant_ref,
                consumer_id=consumer_ids[consumer_ref],
                portfolio_id=portfolio_ids[portfolio_ref],
                subject_id=subject_id,
                client_id="boa-sme-spa",
                scope=scope,
                purpose="SYNTHETIC_PORTFOLIO_MONITORING",
                status=status,
                valid_from=VALID_FROM,
                valid_until=valid_until,
                revoked_at=revoked_at,
                authorization_reference=f"SYNTHETIC-AUTHZ-{grant_ref}",
            )
            .on_conflict_do_nothing(index_elements=[DataAccessGrant.grant_ref])
        )
    return {
        "seedVersion": FI_SEED_VERSION,
        "consumers": len(CONSUMERS),
        "funds": len(PORTFOLIOS),
        "memberships": len(MEMBERSHIPS),
        "grants": len(grant_specs),
    }


__all__ = [
    "CONSUMERS",
    "FI_SEED_VERSION",
    "MEMBERSHIPS",
    "PERFORMANCE_SIZES",
    "PORTFOLIOS",
    "SCOPES",
    "SUBJECTS",
    "seed_financial_intelligence",
]
