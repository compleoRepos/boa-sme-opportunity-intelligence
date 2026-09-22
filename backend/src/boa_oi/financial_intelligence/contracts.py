from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "fi.v1"
CALCULATION_VERSION = "fi-composition-1.0.0"
EXECUTION_MODE = "DETERMINISTIC_RULES"
ML_MODE = "POC_SHADOW"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceStatus(ContractModel):
    source: str
    capability: str
    status: Literal["AVAILABLE", "EMPTY", "UNAVAILABLE", "NOT_IMPLEMENTED"]
    reason: str | None = None


class ResponseMeta(ContractModel):
    contractVersion: Literal["fi.v1"] = "fi.v1"
    asOf: date
    generatedAt: datetime
    traceId: str
    requestId: str
    sources: list[str]
    calculationVersion: str = CALCULATION_VERSION
    featureVersion: str | None = None
    modelVersion: str | None = None
    trainingDatasetVersion: str | None = None
    deploymentMode: Literal["POC_SHADOW"] | None = None
    mlGovernanceStatus: Literal["VERIFIED", "UNAVAILABLE", "NOT_APPLICABLE"]
    sourceStatus: list[SourceStatus]
    partial: bool
    executionMode: Literal["DETERMINISTIC_RULES"] = "DETERMINISTIC_RULES"
    mlMode: Literal["POC_SHADOW"] | None = None
    rulesWeight: float | None = Field(default=None, ge=1.0, le=1.0)
    mlWeight: float | None = Field(default=None, ge=0.0, le=0.0)
    syntheticData: Literal[True] = True
    nonProduction: Literal[True] = True
    downstreamCallCount: int = Field(default=0, ge=0)
    fanOutConcurrency: int = Field(default=0, ge=0)


class MetricProjection(ContractModel):
    metric: str
    period: str
    value: float | None
    previousValue: float | None = None
    growthRate: float | None = None
    unit: str
    dataQuality: str | None = None
    dataCoverage: float | None = Field(default=None, ge=0, le=1)
    sampleSize: int | None = Field(default=None, ge=0)


class VisibilityProjection(ContractModel):
    level: Literal["HIGH", "PARTIAL", "LOW", "UNKNOWN"]
    estimatedShare: float | None = Field(default=None, ge=0, le=1)
    method: str
    categorizationCoverage: float | None = Field(default=None, ge=0, le=1)
    fingerprintCount90d: int | None = Field(default=None, ge=0)
    asOf: date | None = None


class SignalProjection(ContractModel):
    signalRef: str
    type: str
    severity: str
    status: None = None
    stateAsOfStatus: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    value: float
    threshold: float
    asOf: datetime
    ruleVersion: str | None = None
    engineVersion: str | None = None
    evidenceRefs: list[str] = Field(default_factory=list)


class OpportunityProjection(ContractModel):
    opportunityId: str
    opportunityType: str
    status: None = None
    stateAsOfStatus: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    confidence: float = Field(ge=0, le=1)
    priorityScore: float | None = None
    priorityLevel: str | None = None
    horizon: str | None = None
    asOf: datetime
    ruleVersion: str | None = None
    engineVersion: str | None = None
    scoringPolicyId: str | None = None
    scoringPolicyVersion: int | None = None
    fallbackMode: str | None = None
    evidenceRefs: list[str] = Field(default_factory=list)


class CashPosition(ContractModel):
    currency: str
    period: str
    averageBalance: float | None
    minimumBalance: float | None
    maximumBalance: float | None
    balanceTrend: float | None
    concentrationRatio: None = None
    volatility: None = None


class FlowSummary(ContractModel):
    currency: str
    period: str
    inflows: float | None
    outflows: float | None
    netFlow: float | None
    inflowTrend: float | None
    outflowTrend: float | None
    netFlowRatio: float | None
    transactionCount: int | None
    activityTrend: float | None
    concentrationRatio: None = None
    volatility: None = None


class CompanySummary(ContractModel):
    companyId: str
    legalName: str | None
    sector: str | None
    segment: str | None
    status: str | None
    portfolioId: str
    fundId: str
    visibility: VisibilityProjection
    cashPosition: CashPosition
    flowSummary: FlowSummary
    signals: list[SignalProjection]
    opportunities: list[OpportunityProjection]
    metrics: list[MetricProjection]
    disclaimer: Literal["NO_CREDIT_DECISION"] = "NO_CREDIT_DECISION"


class PortfolioSummary(ContractModel):
    portfolioId: str
    fundId: str
    companyCount: int = Field(ge=0)
    companies: list[CompanySummary]
    totalInflows: float | None
    totalOutflows: float | None
    totalNetFlow: float | None
    signalCount: int = Field(ge=0)
    companiesWithSignals: int = Field(ge=0)
    opportunityCount: int = Field(ge=0)
    opportunityDistribution: dict[str, int]
    disclaimer: Literal["NO_CREDIT_DECISION"] = "NO_CREDIT_DECISION"


class PortfolioCatalogItem(ContractModel):
    portfolioId: str
    fundId: str
    name: str
    companyCount: int = Field(ge=0)


class PortfolioCatalog(ContractModel):
    portfolios: list[PortfolioCatalogItem]
    totalCount: int = Field(ge=0)
    pageSize: int = Field(ge=1, le=100)
    nextOffset: int | None = Field(default=None, ge=0)


T = TypeVar("T")


class Envelope(ContractModel, Generic[T]):
    data: T
    meta: ResponseMeta


def response_meta(
    *,
    as_of: date,
    trace_id: str,
    statuses: list[SourceStatus],
    feature_version: str | None = None,
    model_version: str | None = None,
    training_dataset_version: str | None = None,
    downstream_call_count: int = 0,
    fan_out_concurrency: int = 0,
    ml_governance_verified: bool | None = None,
) -> ResponseMeta:
    unique_statuses = list(
        {
            (item.source, item.capability, item.status, item.reason): item for item in statuses
        }.values()
    )
    unique_statuses.sort(key=lambda item: (item.source, item.capability, item.status))
    sources = sorted({item.source for item in unique_statuses})
    return ResponseMeta(
        asOf=as_of,
        generatedAt=datetime.now(timezone.utc),
        traceId=trace_id,
        requestId=trace_id,
        sources=sources,
        sourceStatus=unique_statuses,
        partial=any(item.status == "UNAVAILABLE" for item in unique_statuses),
        featureVersion=feature_version,
        modelVersion=model_version,
        trainingDatasetVersion=training_dataset_version,
        downstreamCallCount=downstream_call_count,
        fanOutConcurrency=fan_out_concurrency,
        mlGovernanceStatus=(
            "VERIFIED"
            if ml_governance_verified is True
            else "UNAVAILABLE"
            if ml_governance_verified is False
            else "NOT_APPLICABLE"
        ),
        deploymentMode="POC_SHADOW" if ml_governance_verified is True else None,
        mlMode="POC_SHADOW" if ml_governance_verified is True else None,
        rulesWeight=1.0 if ml_governance_verified is True else None,
        mlWeight=0.0 if ml_governance_verified is True else None,
    )


def no_raw_financial_fields(payload: Any) -> bool:
    forbidden = {
        "iban",
        "accountid",
        "accountnumber",
        "transactionid",
        "transactions",
        "counterparty",
        "counterpartyname",
        "remittanceinformation",
    }

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            if any(str(key).replace("_", "").lower() in forbidden for key in value):
                return False
            return all(walk(item) for item in value.values())
        if isinstance(value, list):
            return all(walk(item) for item in value)
        return True

    return walk(payload)


__all__ = [
    "CALCULATION_VERSION",
    "CONTRACT_VERSION",
    "CashPosition",
    "CompanySummary",
    "Envelope",
    "FlowSummary",
    "MetricProjection",
    "OpportunityProjection",
    "PortfolioCatalog",
    "PortfolioCatalogItem",
    "PortfolioSummary",
    "ResponseMeta",
    "SignalProjection",
    "SourceStatus",
    "VisibilityProjection",
    "no_raw_financial_fields",
    "response_meta",
]
