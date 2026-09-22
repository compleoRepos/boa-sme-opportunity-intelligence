from __future__ import annotations

import asyncio
import os
from collections import Counter
from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.financial_intelligence.authorization import (
    AuthorizationContext,
    authorize,
    list_authorized_portfolios,
)
from boa_oi.financial_intelligence.contracts import (
    CashPosition,
    CompanySummary,
    Envelope,
    FlowSummary,
    OpportunityProjection,
    PortfolioCatalog,
    PortfolioCatalogItem,
    PortfolioSummary,
    SignalProjection,
    SourceStatus,
    no_raw_financial_fields,
    response_meta,
)
from boa_oi.financial_intelligence.service import FinancialIntelligenceComposer
from boa_oi.financial_intelligence_models import ExternalPortfolio, ExternalPortfolioCompany
from boa_oi.platform import (
    Principal,
    Problem,
    correlation_id,
    create_service_app,
    current_principal,
    get_session,
    reject_unknown_filters,
)

app = create_service_app(
    "financial-intelligence-service",
    "Read-only, synthetic, deterministic Financial Intelligence composition API. "
    "No credit decision.",
)
PREFIX = "/internal/v1/financial-intelligence"
composer = FinancialIntelligenceComposer()


async def _authorized_company(
    *,
    request: Request,
    principal: Principal,
    session: Session,
    company_id: str,
    required_scope: str,
    as_of: date,
) -> tuple[
    AuthorizationContext,
    CompanySummary,
    list[SourceStatus],
    str | None,
    str | None,
    str | None,
    bool,
]:
    context = authorize(
        session,
        request=request,
        principal=principal,
        required_scopes=("financial.read", required_scope),
        company_ref=company_id,
        membership_at=datetime.combine(as_of, datetime.max.time(), tzinfo=timezone.utc),
    )
    (
        summary,
        statuses,
        feature_version,
        model_version,
        training_dataset_version,
        ml_governance_verified,
    ) = await composer.company_summary(
        company_id,
        portfolio_id=context.portfolio_ref,
        fund_id=context.fund_ref,
        as_of=as_of,
        trace_id=correlation_id(request),
    )
    return (
        context,
        summary,
        statuses,
        feature_version,
        model_version,
        training_dataset_version,
        ml_governance_verified,
    )


def _envelope(
    data: Any,
    *,
    request: Request,
    as_of: date,
    statuses: list[SourceStatus],
    feature_version: str | None = None,
    model_version: str | None = None,
    training_dataset_version: str | None = None,
    downstream_call_count: int = 0,
    fan_out_concurrency: int = 0,
    ml_governance_verified: bool | None = None,
) -> dict[str, Any]:
    result = {
        "data": data.model_dump(mode="json") if hasattr(data, "model_dump") else data,
        "meta": response_meta(
            as_of=as_of,
            trace_id=correlation_id(request),
            statuses=statuses,
            feature_version=feature_version,
            model_version=model_version,
            training_dataset_version=training_dataset_version,
            downstream_call_count=downstream_call_count,
            fan_out_concurrency=fan_out_concurrency,
            ml_governance_verified=ml_governance_verified,
        ).model_dump(mode="json"),
    }
    if not no_raw_financial_fields(result):
        raise Problem(500, "FI_MINIMIZATION_FAILURE", "The FI response failed data minimization.")
    return result


@app.get(
    f"{PREFIX}/portfolios",
    response_model=Envelope[PortfolioCatalog],
    operation_id="fi_portfolio_catalog",
    tags=["Financial Intelligence"],
)
def portfolio_catalog(
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf", "pageSize", "offset"})
    contexts = list_authorized_portfolios(
        session,
        request=request,
        principal=principal,
        required_scopes=("financial.read", "portfolio.read"),
    )
    as_of_time = datetime.combine(as_of, datetime.max.time(), tzinfo=timezone.utc)
    visible_contexts = contexts[offset : offset + page_size]
    items: list[PortfolioCatalogItem] = []
    for context in visible_contexts:
        portfolio = session.get(ExternalPortfolio, context.portfolio_id)
        company_count = session.scalar(
            select(func.count(ExternalPortfolioCompany.id)).where(
                ExternalPortfolioCompany.portfolio_id == context.portfolio_id,
                ExternalPortfolioCompany.valid_from <= as_of_time,
                (ExternalPortfolioCompany.valid_until.is_(None))
                | (ExternalPortfolioCompany.valid_until > as_of_time),
            )
        )
        items.append(
            PortfolioCatalogItem(
                portfolioId=context.portfolio_ref,
                fundId=context.fund_ref,
                name=portfolio.display_name if portfolio else context.portfolio_ref,
                companyCount=int(company_count or 0),
            )
        )
    statuses = [
        SourceStatus(
            source="financial-intelligence-service",
            capability="portfolio-authorization",
            status="AVAILABLE",
        )
    ]
    return _envelope(
        PortfolioCatalog(
            portfolios=items,
            totalCount=len(contexts),
            pageSize=page_size,
            nextOffset=offset + page_size if offset + page_size < len(contexts) else None,
        ),
        request=request,
        as_of=as_of,
        statuses=statuses,
    )


@app.get(
    f"{PREFIX}/portfolios/{{portfolio_id}}/summary",
    response_model=Envelope[PortfolioSummary],
    operation_id="fi_portfolio_summary",
    tags=["Financial Intelligence"],
)
async def portfolio_summary(
    portfolio_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf"})
    context = authorize(
        session,
        request=request,
        principal=principal,
        required_scopes=("financial.read", "portfolio.read"),
        portfolio_ref=portfolio_id,
    )
    as_of_time = datetime.combine(as_of, datetime.max.time(), tzinfo=timezone.utc)
    maximum_companies = max(1, min(int(os.getenv("FI_MAX_PORTFOLIO_COMPANIES", "500")), 500))
    memberships = list(
        session.scalars(
            select(ExternalPortfolioCompany)
            .where(
                ExternalPortfolioCompany.portfolio_id == context.portfolio_id,
                ExternalPortfolioCompany.valid_from <= as_of_time,
                (ExternalPortfolioCompany.valid_until.is_(None))
                | (ExternalPortfolioCompany.valid_until > as_of_time),
            )
            .order_by(ExternalPortfolioCompany.company_ref)
            .limit(maximum_companies + 1)
        )
    )
    if len(memberships) > maximum_companies:
        raise Problem(
            422,
            "FI_PORTFOLIO_LIMIT_EXCEEDED",
            f"Portfolio composition is limited to {maximum_companies} companies per request.",
        )
    concurrency = max(1, min(int(os.getenv("FI_PORTFOLIO_CONCURRENCY", "10")), 25))
    semaphore = asyncio.Semaphore(concurrency)

    async def compose_company(
        membership: ExternalPortfolioCompany,
    ) -> tuple[CompanySummary, list[SourceStatus], str | None, str | None, str | None, bool]:
        async with semaphore:
            return await composer.company_summary(
                membership.company_ref,
                portfolio_id=context.portfolio_ref,
                fund_id=context.fund_ref,
                as_of=as_of,
                trace_id=correlation_id(request),
            )

    composed = await asyncio.gather(*(compose_company(item) for item in memberships))
    companies: list[CompanySummary] = []
    statuses: list[SourceStatus] = []
    feature_version = None
    model_version = None
    training_dataset_version = None
    governance_results: list[bool] = []
    for (
        company,
        company_statuses,
        feature,
        model,
        training_dataset,
        governance_verified,
    ) in composed:
        companies.append(company)
        statuses.extend(company_statuses)
        feature_version = feature_version or feature
        model_version = model_version or model
        training_dataset_version = training_dataset_version or training_dataset
        governance_results.append(governance_verified)
    flow_values = [item.flowSummary for item in companies]
    inflows = [item.inflows for item in flow_values if item.inflows is not None]
    outflows = [item.outflows for item in flow_values if item.outflows is not None]
    opportunity_distribution = Counter(
        opportunity.opportunityType
        for company in companies
        for opportunity in company.opportunities
    )
    statuses.append(
        SourceStatus(
            source="financial-intelligence-service",
            capability="portfolio-flow-evolution",
            status="NOT_IMPLEMENTED",
            reason="fi.v1 does not expose a portfolio time series.",
        )
    )
    data = PortfolioSummary(
        portfolioId=context.portfolio_ref,
        fundId=context.fund_ref,
        companyCount=len(companies),
        companies=companies,
        totalInflows=sum(inflows) if inflows else None,
        totalOutflows=sum(outflows) if outflows else None,
        totalNetFlow=(sum(inflows) - sum(outflows)) if inflows and outflows else None,
        signalCount=sum(len(item.signals) for item in companies),
        companiesWithSignals=sum(bool(item.signals) for item in companies),
        opportunityCount=sum(len(item.opportunities) for item in companies),
        opportunityDistribution=dict(sorted(opportunity_distribution.items())),
    )
    return _envelope(
        data,
        request=request,
        as_of=as_of,
        statuses=statuses,
        feature_version=feature_version,
        model_version=model_version,
        training_dataset_version=training_dataset_version,
        downstream_call_count=len(memberships) * 5,
        fan_out_concurrency=min(concurrency, len(memberships)),
        ml_governance_verified=(all(governance_results) if governance_results else None),
    )


@app.get(
    f"{PREFIX}/companies/{{company_id}}/summary",
    response_model=Envelope[CompanySummary],
    operation_id="fi_company_summary",
    tags=["Financial Intelligence"],
)
async def company_summary(
    company_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf"})
    (
        _context,
        summary,
        statuses,
        feature,
        model,
        training_dataset,
        governance_verified,
    ) = await _authorized_company(
        request=request,
        principal=principal,
        session=session,
        company_id=company_id,
        required_scope="financial.read",
        as_of=as_of,
    )
    return _envelope(
        summary,
        request=request,
        as_of=as_of,
        statuses=statuses,
        feature_version=feature,
        model_version=model,
        training_dataset_version=training_dataset,
        downstream_call_count=5,
        fan_out_concurrency=5,
        ml_governance_verified=governance_verified,
    )


@app.get(
    f"{PREFIX}/companies/{{company_id}}/signals",
    response_model=Envelope[list[SignalProjection]],
    operation_id="fi_company_signals",
    tags=["Financial Intelligence"],
)
async def company_signals(
    company_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf"})
    (
        _context,
        summary,
        statuses,
        feature,
        model,
        training_dataset,
        governance_verified,
    ) = await _authorized_company(
        request=request,
        principal=principal,
        session=session,
        company_id=company_id,
        required_scope="signals.read",
        as_of=as_of,
    )
    return _envelope(
        summary.signals,
        request=request,
        as_of=as_of,
        statuses=statuses,
        feature_version=feature,
        model_version=model,
        training_dataset_version=training_dataset,
        downstream_call_count=5,
        fan_out_concurrency=5,
        ml_governance_verified=governance_verified,
    )


@app.get(
    f"{PREFIX}/companies/{{company_id}}/opportunities",
    response_model=Envelope[list[OpportunityProjection]],
    operation_id="fi_company_opportunities",
    tags=["Financial Intelligence"],
)
async def company_opportunities(
    company_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf"})
    (
        _context,
        summary,
        statuses,
        feature,
        model,
        training_dataset,
        governance_verified,
    ) = await _authorized_company(
        request=request,
        principal=principal,
        session=session,
        company_id=company_id,
        required_scope="opportunities.read",
        as_of=as_of,
    )
    return _envelope(
        summary.opportunities,
        request=request,
        as_of=as_of,
        statuses=statuses,
        feature_version=feature,
        model_version=model,
        training_dataset_version=training_dataset,
        downstream_call_count=5,
        fan_out_concurrency=5,
        ml_governance_verified=governance_verified,
    )


@app.get(
    f"{PREFIX}/companies/{{company_id}}/cash-position",
    response_model=Envelope[CashPosition],
    operation_id="fi_company_cash_position",
    tags=["Financial Intelligence"],
)
async def company_cash_position(
    company_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf"})
    (
        _context,
        summary,
        statuses,
        feature,
        model,
        training_dataset,
        governance_verified,
    ) = await _authorized_company(
        request=request,
        principal=principal,
        session=session,
        company_id=company_id,
        required_scope="financial.read",
        as_of=as_of,
    )
    return _envelope(
        summary.cashPosition,
        request=request,
        as_of=as_of,
        statuses=statuses,
        feature_version=feature,
        model_version=model,
        training_dataset_version=training_dataset,
        downstream_call_count=5,
        fan_out_concurrency=5,
        ml_governance_verified=governance_verified,
    )


@app.get(
    f"{PREFIX}/companies/{{company_id}}/flow-summary",
    response_model=Envelope[FlowSummary],
    operation_id="fi_company_flow_summary",
    tags=["Financial Intelligence"],
)
async def company_flow_summary(
    company_id: str,
    request: Request,
    as_of: Annotated[date, Query(alias="asOf")],
    principal: Principal = Depends(current_principal),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reject_unknown_filters(request, {"asOf"})
    (
        _context,
        summary,
        statuses,
        feature,
        model,
        training_dataset,
        governance_verified,
    ) = await _authorized_company(
        request=request,
        principal=principal,
        session=session,
        company_id=company_id,
        required_scope="financial.read",
        as_of=as_of,
    )
    return _envelope(
        summary.flowSummary,
        request=request,
        as_of=as_of,
        statuses=statuses,
        feature_version=feature,
        model_version=model,
        training_dataset_version=training_dataset,
        downstream_call_count=5,
        fan_out_concurrency=5,
        ml_governance_verified=governance_verified,
    )


@app.get(
    f"{PREFIX}/companies/{{company_id}}/{{projection}}",
    include_in_schema=False,
)
async def unsupported_projection(
    company_id: str,
    projection: Literal["credit-decision"],
) -> None:
    del company_id, projection
    raise Problem(404, "RESOURCE_NOT_FOUND", "Financial Intelligence resource was not found.")


__all__ = ["app", "composer"]
