from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.financial_intelligence_models import (
    DataAccessGrant,
    ExternalConsumer,
    ExternalPortfolio,
    ExternalPortfolioCompany,
    FinancialIntelligenceAccessAudit,
)
from boa_oi.platform import Principal, Problem, correlation_id

ALLOWED_ROLES = frozenset({"EXTERNAL_CONSUMER"})
FI_PURPOSE = "SYNTHETIC_PORTFOLIO_MONITORING"


@dataclass(frozen=True)
class AuthorizationContext:
    consumer_id: UUID
    consumer_ref: str
    portfolio_id: UUID
    portfolio_ref: str
    fund_ref: str
    company_ref: str | None
    grants: tuple[DataAccessGrant, ...]

    @property
    def authorization_reference(self) -> str:
        return ",".join(sorted(grant.authorization_reference for grant in self.grants))


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def grant_is_active(grant: DataAccessGrant, *, now: datetime) -> bool:
    return (
        grant.status == "ACTIVE"
        and grant.revoked_at is None
        and _utc(grant.valid_from) <= now
        and now < _utc(grant.valid_until)
    )


def _audit(
    session: Session,
    *,
    request: Request,
    principal: Principal,
    required_scope: str,
    result: str,
    reason_code: str,
    consumer_id: UUID | None = None,
    portfolio_ref: str | None = None,
    company_ref: str | None = None,
    authorization_reference: str | None = None,
    purpose: str | None = None,
) -> None:
    session.add(
        FinancialIntelligenceAccessAudit(
            id=uuid4(),
            consumer_id=consumer_id,
            subject_id=principal.subject,
            client_id=principal.client_id,
            portfolio_ref=portfolio_ref,
            company_ref=company_ref,
            endpoint=request.url.path,
            required_scope=required_scope,
            trace_id=correlation_id(request),
            result=result,
            reason_code=reason_code,
            authorization_reference=authorization_reference,
            purpose=purpose,
            safe_details=None,
        )
    )
    # Authorization decisions must survive the request error transaction. The audit contains
    # no token and no financial payload; committing it here also prevents later rollback loss.
    session.commit()


def authorize(
    session: Session,
    *,
    request: Request,
    principal: Principal,
    required_scopes: tuple[str, ...],
    portfolio_ref: str | None = None,
    company_ref: str | None = None,
    now: datetime | None = None,
    membership_at: datetime | None = None,
) -> AuthorizationContext:
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    membership_checked_at = (membership_at or checked_at).astimezone(timezone.utc)
    primary_scope = required_scopes[-1]
    if principal.roles.isdisjoint(ALLOWED_ROLES):
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="ROLE_FORBIDDEN",
            portfolio_ref=portfolio_ref,
            company_ref=company_ref,
        )
        raise Problem(403, "FORBIDDEN", "The authenticated principal lacks an FI role.")

    client_id = principal.client_id
    if not client_id:
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="CLIENT_BINDING_MISSING",
            portfolio_ref=portfolio_ref,
            company_ref=company_ref,
        )
        raise Problem(
            403,
            "FI_CLIENT_BINDING_REQUIRED",
            "Financial Intelligence access requires an explicit OAuth client binding.",
        )

    missing = [scope for scope in required_scopes if scope not in principal.scopes]
    if missing:
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="SCOPE_MISSING",
            portfolio_ref=portfolio_ref,
            company_ref=company_ref,
        )
        raise Problem(
            403, "FI_SCOPE_MISSING", "An explicit Financial Intelligence scope is required."
        )

    stmt = (
        select(DataAccessGrant, ExternalConsumer, ExternalPortfolio)
        .join(ExternalConsumer, DataAccessGrant.consumer_id == ExternalConsumer.id)
        .join(ExternalPortfolio, DataAccessGrant.portfolio_id == ExternalPortfolio.id)
        .where(
            DataAccessGrant.subject_id == principal.subject,
            DataAccessGrant.client_id == client_id,
            DataAccessGrant.purpose == FI_PURPOSE,
            ExternalPortfolio.consumer_id == ExternalConsumer.id,
            ExternalConsumer.status == "ACTIVE",
            ExternalPortfolio.status == "ACTIVE",
        )
    )
    if portfolio_ref is not None:
        stmt = stmt.where(ExternalPortfolio.portfolio_ref == portfolio_ref)
    rows = list(session.execute(stmt).tuples())
    active_rows = [row for row in rows if grant_is_active(row[0], now=checked_at)]
    grouped: dict[UUID, list[tuple[DataAccessGrant, ExternalConsumer, ExternalPortfolio]]] = {}
    for row in active_rows:
        grouped.setdefault(row[2].id, []).append(row)
    eligible = [
        rows_for_portfolio
        for rows_for_portfolio in grouped.values()
        if set(required_scopes) <= {item[0].scope for item in rows_for_portfolio}
    ]
    scope_eligible_count = len(eligible)
    if company_ref is not None and portfolio_ref is None and eligible:
        candidate_ids = [rows_for_portfolio[0][2].id for rows_for_portfolio in eligible]
        memberships = session.scalars(
            select(ExternalPortfolioCompany).where(
                ExternalPortfolioCompany.portfolio_id.in_(candidate_ids),
                ExternalPortfolioCompany.company_ref == company_ref,
            )
        ).all()
        active_membership_portfolio_ids = {
            membership.portfolio_id
            for membership in memberships
            if _utc(membership.valid_from) <= membership_checked_at
            and (
                membership.valid_until is None
                or membership_checked_at < _utc(membership.valid_until)
            )
        }
        eligible = [
            rows_for_portfolio
            for rows_for_portfolio in eligible
            if rows_for_portfolio[0][2].id in active_membership_portfolio_ids
        ]
        security_domains = {rows_for_portfolio[0][1].id for rows_for_portfolio in eligible}
        if len(security_domains) == 1 and len(eligible) > 1:
            eligible = [min(eligible, key=lambda item: item[0][2].portfolio_ref)]
    active_portfolio_rows = [
        rows_for_portfolio for rows_for_portfolio in grouped.values() if rows_for_portfolio
    ]
    if len(eligible) == 0 and scope_eligible_count == 0 and len(active_portfolio_rows) == 1:
        row = active_portfolio_rows[0][0]
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="GRANT_SCOPE_MISSING",
            consumer_id=row[1].id,
            portfolio_ref=row[2].portfolio_ref,
            company_ref=company_ref,
        )
        raise Problem(
            403, "FI_SCOPE_MISSING", "An explicit Financial Intelligence grant scope is required."
        )
    if len(eligible) != 1:
        consumer_id = rows[0][1].id if rows else None
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="GRANT_OR_RESOURCE_NOT_FOUND",
            consumer_id=consumer_id,
            portfolio_ref=portfolio_ref,
            company_ref=company_ref,
        )
        raise Problem(404, "RESOURCE_NOT_FOUND", "Financial Intelligence resource was not found.")

    selected = eligible[0]
    consumer = selected[0][1]
    portfolio = selected[0][2]
    if not set(required_scopes) <= set(consumer.allowed_scopes or []):
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="CONSUMER_SCOPE_MISSING",
            consumer_id=consumer.id,
            portfolio_ref=portfolio.portfolio_ref,
            company_ref=company_ref,
        )
        raise Problem(
            403,
            "FI_SCOPE_MISSING",
            "The Financial Intelligence scope is not enabled for this consumer.",
        )
    if company_ref is not None:
        membership = session.scalar(
            select(ExternalPortfolioCompany).where(
                ExternalPortfolioCompany.portfolio_id == portfolio.id,
                ExternalPortfolioCompany.company_ref == company_ref,
            )
        )
        if (
            membership is None
            or _utc(membership.valid_from) > membership_checked_at
            or (
                membership.valid_until is not None
                and membership_checked_at >= _utc(membership.valid_until)
            )
        ):
            _audit(
                session,
                request=request,
                principal=principal,
                required_scope=primary_scope,
                result="DENY",
                reason_code="COMPANY_NOT_IN_PORTFOLIO",
                consumer_id=consumer.id,
                portfolio_ref=portfolio.portfolio_ref,
                company_ref=company_ref,
            )
            raise Problem(
                404, "RESOURCE_NOT_FOUND", "Financial Intelligence resource was not found."
            )

    grants_by_scope = {item[0].scope: item[0] for item in selected}
    grants = tuple(grants_by_scope[scope] for scope in required_scopes)
    reference = ",".join(sorted(grant.authorization_reference for grant in grants))
    purpose = ",".join(sorted({grant.purpose for grant in grants}))
    _audit(
        session,
        request=request,
        principal=principal,
        required_scope=primary_scope,
        result="ALLOW",
        reason_code="AUTHORIZED",
        consumer_id=consumer.id,
        portfolio_ref=portfolio.portfolio_ref,
        company_ref=company_ref,
        authorization_reference=reference,
        purpose=purpose,
    )
    return AuthorizationContext(
        consumer_id=consumer.id,
        consumer_ref=consumer.consumer_ref,
        portfolio_id=portfolio.id,
        portfolio_ref=portfolio.portfolio_ref,
        fund_ref=portfolio.fund_ref,
        company_ref=company_ref,
        grants=grants,
    )


def list_authorized_portfolios(
    session: Session,
    *,
    request: Request,
    principal: Principal,
    required_scopes: tuple[str, ...],
    now: datetime | None = None,
) -> list[AuthorizationContext]:
    primary_scope = required_scopes[0]
    if not ALLOWED_ROLES.intersection(principal.roles):
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="ROLE_MISSING",
        )
        raise Problem(403, "FI_ROLE_MISSING", "Financial Intelligence access is not allowed.")
    client_id = principal.client_id
    if not client_id:
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="CLIENT_BINDING_MISSING",
        )
        raise Problem(
            403,
            "FI_CLIENT_BINDING_REQUIRED",
            "Financial Intelligence access requires an explicit OAuth client binding.",
        )
    missing_scopes = sorted(set(required_scopes) - principal.scopes)
    if missing_scopes:
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="SCOPE_MISSING",
        )
        raise Problem(403, "FI_SCOPE_MISSING", "Required Financial Intelligence scope is missing.")

    checked_at = now or datetime.now(timezone.utc)
    rows = session.execute(
        select(DataAccessGrant, ExternalConsumer, ExternalPortfolio)
        .join(ExternalConsumer, DataAccessGrant.consumer_id == ExternalConsumer.id)
        .join(ExternalPortfolio, DataAccessGrant.portfolio_id == ExternalPortfolio.id)
        .where(
            DataAccessGrant.subject_id == principal.subject,
            DataAccessGrant.client_id == client_id,
            DataAccessGrant.purpose == FI_PURPOSE,
            DataAccessGrant.scope.in_(required_scopes),
            ExternalPortfolio.consumer_id == ExternalConsumer.id,
            ExternalConsumer.status == "ACTIVE",
            ExternalPortfolio.status == "ACTIVE",
        )
        .order_by(ExternalPortfolio.portfolio_ref, DataAccessGrant.scope)
    ).all()
    grouped: dict[UUID, list[tuple[DataAccessGrant, ExternalConsumer, ExternalPortfolio]]] = {}
    for grant, consumer, portfolio in rows:
        if grant_is_active(grant, now=checked_at):
            grouped.setdefault(portfolio.id, []).append((grant, consumer, portfolio))

    contexts: list[AuthorizationContext] = []
    for portfolio_rows in grouped.values():
        consumer = portfolio_rows[0][1]
        portfolio = portfolio_rows[0][2]
        grants_by_scope = {grant.scope: grant for grant, _consumer, _portfolio in portfolio_rows}
        if not set(required_scopes) <= set(grants_by_scope):
            continue
        if not set(required_scopes) <= set(consumer.allowed_scopes or []):
            continue
        grants = tuple(grants_by_scope[scope] for scope in required_scopes)
        context = AuthorizationContext(
            consumer_id=consumer.id,
            consumer_ref=consumer.consumer_ref,
            portfolio_id=portfolio.id,
            portfolio_ref=portfolio.portfolio_ref,
            fund_ref=portfolio.fund_ref,
            company_ref=None,
            grants=grants,
        )
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="ALLOW",
            reason_code="AUTHORIZED",
            consumer_id=context.consumer_id,
            portfolio_ref=context.portfolio_ref,
            authorization_reference=context.authorization_reference,
            purpose=",".join(sorted({grant.purpose for grant in grants})),
        )
        contexts.append(context)

    if not contexts:
        _audit(
            session,
            request=request,
            principal=principal,
            required_scope=primary_scope,
            result="DENY",
            reason_code="GRANT_OR_RESOURCE_NOT_FOUND",
        )
        raise Problem(404, "RESOURCE_NOT_FOUND", "Financial Intelligence resource was not found.")
    return contexts


__all__ = [
    "FI_PURPOSE",
    "AuthorizationContext",
    "authorize",
    "grant_is_active",
    "list_authorized_portfolios",
]
