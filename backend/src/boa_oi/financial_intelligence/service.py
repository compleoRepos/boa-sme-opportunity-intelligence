from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from typing import Any, TypeGuard

from boa_oi.financial_intelligence.contracts import (
    CashPosition,
    CompanySummary,
    FlowSummary,
    MetricProjection,
    OpportunityProjection,
    SignalProjection,
    SourceStatus,
    VisibilityProjection,
)
from boa_oi.http_clients import service_request
from boa_oi.platform import Problem

OWNER_ENV = {
    "customer": "CUSTOMER_SERVICE_URL",
    "analytics": "ANALYTICS_SERVICE_URL",
    "signal": "SIGNAL_SERVICE_URL",
    "opportunity": "OPPORTUNITY_SERVICE_URL",
    "portfolio": "PORTFOLIO_SERVICE_URL",
}
FI_TIMEOUT_SECONDS = float(os.getenv("FI_DEPENDENCY_TIMEOUT_SECONDS", "5.0"))


def _is_json_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class OwnerClients:
    def _url(self, owner: str) -> str:
        value = os.getenv(OWNER_ENV[owner])
        if not value:
            raise Problem(
                503,
                "DEPENDENCY_CONFIGURATION_ERROR",
                f"{OWNER_ENV[owner]} is not configured.",
            )
        return value.rstrip("/")

    async def get(
        self,
        owner: str,
        path: str,
        *,
        trace_id: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        # La frontière FI valide le consommateur externe. Les domaines propriétaires
        # reçoivent uniquement l'identité technique FI, jamais le bearer B2B entrant.
        return await service_request(
            "GET",
            f"{self._url(owner)}/internal/v1/{path.lstrip('/')}",
            correlation_id=trace_id,
            params=params,
            timeout=FI_TIMEOUT_SECONDS,
        )


async def _source(
    name: str,
    capability: str,
    operation: Any,
) -> tuple[str, Any | None, SourceStatus]:
    try:
        payload = await operation
    except Problem as exc:
        return (
            name,
            None,
            SourceStatus(
                source=name,
                capability=capability,
                status="UNAVAILABLE",
                reason=exc.code,
            ),
        )
    return (
        name,
        payload,
        SourceStatus(
            source=name,
            capability=capability,
            status="AVAILABLE" if payload else "EMPTY",
        ),
    )


def _metric_rows(payload: Any, *, as_of: date) -> list[dict[str, Any]]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return [
        row
        for row in rows
        if row.get("asOf") == as_of.isoformat() and row.get("period") in {"30D", "90D", "365D"}
    ]


def _latest_by_metric(rows: list[dict[str, Any]], period: str = "90D") -> dict[str, dict[str, Any]]:
    return {str(row["metric"]): row for row in rows if row.get("period") == period}


def metric_projection(row: dict[str, Any]) -> MetricProjection:
    metric = str(row["metric"])
    unit = (
        "COUNT"
        if metric.endswith("_count") or metric == "transaction_count"
        else "PERCENT"
        if any(token in metric for token in ("ratio", "rate", "share", "utilization"))
        else "MAD"
    )
    return MetricProjection(
        metric=metric,
        period=str(row["period"]),
        value=row.get("currentValue"),
        previousValue=row.get("previousPeriodValue"),
        growthRate=row.get("growthRate"),
        unit=unit,
        dataQuality=row.get("dataQuality"),
        dataCoverage=row.get("dataCoverage"),
        sampleSize=row.get("sampleSize"),
    )


def cash_position(metrics: dict[str, dict[str, Any]]) -> CashPosition:
    average = metrics.get("average_balance", {})
    minimum = metrics.get("minimum_balance", {})
    maximum = metrics.get("maximum_balance", {})
    return CashPosition(
        currency="MAD",
        period="90D",
        averageBalance=average.get("currentValue"),
        minimumBalance=minimum.get("currentValue"),
        maximumBalance=maximum.get("currentValue"),
        balanceTrend=average.get("growthRate"),
        concentrationRatio=None,
        volatility=None,
    )


def flow_summary(metrics: dict[str, dict[str, Any]]) -> FlowSummary:
    inflow = metrics.get("inflow_amount", {})
    outflow = metrics.get("outflow_amount", {})
    activity = metrics.get("transaction_count", {})
    inflows = inflow.get("currentValue")
    outflows = outflow.get("currentValue")
    net = float(inflows) - float(outflows) if inflows is not None and outflows is not None else None
    denominator = abs(float(outflows)) if outflows is not None and float(outflows) != 0 else None
    return FlowSummary(
        currency="MAD",
        period="90D",
        inflows=inflows,
        outflows=outflows,
        netFlow=net,
        inflowTrend=inflow.get("growthRate"),
        outflowTrend=outflow.get("growthRate"),
        netFlowRatio=net / denominator if net is not None and denominator else None,
        transactionCount=(
            int(activity["currentValue"]) if activity.get("currentValue") is not None else None
        ),
        activityTrend=activity.get("growthRate"),
        concentrationRatio=None,
        volatility=None,
    )


def visibility_projection(customer: dict[str, Any] | None) -> VisibilityProjection:
    raw = (customer or {}).get("flowVisibility") or {}
    return VisibilityProjection(
        level=raw.get("level", "UNKNOWN"),
        estimatedShare=raw.get("estimatedShare"),
        method=raw.get("method", "NONE"),
        categorizationCoverage=raw.get("categorizationCoverage"),
        fingerprintCount90d=raw.get("fingerprintCount90d"),
        asOf=raw.get("asOf"),
    )


def signal_projection(payload: Any, *, as_of: date) -> list[SignalProjection]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    result = []
    from_date = as_of - timedelta(days=364)
    for row in rows:
        detected = row.get("detectedAt")
        if not detected:
            continue
        detected_date = date.fromisoformat(str(detected)[:10])
        if not from_date <= detected_date <= as_of:
            continue
        result.append(
            SignalProjection(
                signalRef=str(row["signalId"]),
                type=str(row["type"]),
                severity=str(row["severity"]),
                status=None,
                value=float(row["value"]),
                threshold=float(row["threshold"]),
                asOf=detected,
                ruleVersion=row.get("ruleVersion"),
                engineVersion=row.get("engineVersion"),
                evidenceRefs=[
                    str(value) for value in row.get("metricReferences", []) if value is not None
                ],
            )
        )
    return result


def opportunity_projection(payload: Any, *, as_of: date) -> list[OpportunityProjection]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    result = []
    from_date = as_of - timedelta(days=364)
    for row in rows:
        generated = row.get("generatedAt")
        if not generated:
            continue
        generated_date = date.fromisoformat(str(generated)[:10])
        if not from_date <= generated_date <= as_of:
            continue
        result.append(
            OpportunityProjection(
                opportunityId=str(row["opportunityId"]),
                opportunityType=str(row["opportunityType"]),
                status=None,
                confidence=float(row["confidence"]),
                priorityScore=row.get("priorityScore"),
                priorityLevel=row.get("priorityLevel"),
                horizon=row.get("horizon"),
                asOf=generated,
                ruleVersion=row.get("ruleVersion"),
                engineVersion=row.get("engineVersion"),
                scoringPolicyId=row.get("scoringPolicyId"),
                scoringPolicyVersion=row.get("scoringPolicyVersion"),
                fallbackMode=row.get("fallbackMode"),
                evidenceRefs=[f"{row['opportunityId']}:explanation"]
                if int(row.get("evidenceCount") or 0) > 0
                else [],
            )
        )
    return result


class FinancialIntelligenceComposer:
    def __init__(self, clients: OwnerClients | None = None) -> None:
        self.clients = clients or OwnerClients()

    async def company_summary(
        self,
        company_id: str,
        *,
        portfolio_id: str,
        fund_id: str,
        as_of: date,
        trace_id: str,
    ) -> tuple[
        CompanySummary,
        list[SourceStatus],
        str | None,
        str | None,
        str | None,
        bool,
    ]:
        from_date = as_of - timedelta(days=364)
        to_date = as_of + timedelta(days=1)
        calls = await asyncio.gather(
            _source(
                "customer-service",
                "company-profile-and-lot15-visibility",
                self.clients.get(
                    "customer",
                    f"customers/{company_id}",
                    trace_id=trace_id,
                    params={"asOf": as_of.isoformat()},
                ),
            ),
            _source(
                "analytics-service",
                "booked-point-in-time-metrics",
                self.clients.get(
                    "analytics",
                    f"customers/{company_id}/metrics",
                    trace_id=trace_id,
                    params={
                        "pageSize": 1000,
                        "fromDate": as_of.isoformat(),
                        "toDate": to_date.isoformat(),
                    },
                ),
            ),
            _source(
                "signal-service",
                "persisted-signals",
                self.clients.get(
                    "signal",
                    f"customers/{company_id}/signals",
                    trace_id=trace_id,
                    params={
                        "pageSize": 1000,
                        "fromDate": from_date.isoformat(),
                        "toDate": to_date.isoformat(),
                    },
                ),
            ),
            _source(
                "opportunity-service",
                "persisted-opportunities",
                self.clients.get(
                    "opportunity",
                    f"customers/{company_id}/opportunities",
                    trace_id=trace_id,
                    params={
                        "pageSize": 1000,
                        "fromDate": from_date.isoformat(),
                        "toDate": to_date.isoformat(),
                    },
                ),
            ),
            _source(
                "portfolio-service",
                "rules-only-commercial-projection",
                self.clients.get(
                    "portfolio",
                    f"customers/{company_id}/propensity",
                    trace_id=trace_id,
                    params={"asOf": as_of.isoformat()},
                ),
            ),
        )
        payloads = {name: payload for name, payload, _status in calls}
        statuses = [status for _name, _payload, status in calls]
        rows = _metric_rows(payloads.get("analytics-service"), as_of=as_of)
        metrics_90d = _latest_by_metric(rows)
        cash = cash_position(metrics_90d)
        flows = flow_summary(metrics_90d)
        if cash.concentrationRatio is None:
            statuses.append(
                SourceStatus(
                    source="analytics-service",
                    capability="cash-concentration",
                    status="NOT_IMPLEMENTED",
                    reason="No owner aggregate supports this calculation without raw data.",
                )
            )
        if cash.volatility is None:
            statuses.append(
                SourceStatus(
                    source="analytics-service",
                    capability="cash-volatility",
                    status="NOT_IMPLEMENTED",
                    reason="No owner aggregate supports this calculation without raw data.",
                )
            )
        if flows.concentrationRatio is None:
            statuses.append(
                SourceStatus(
                    source="analytics-service",
                    capability="flow-concentration",
                    status="NOT_IMPLEMENTED",
                    reason="No owner aggregate supports this calculation without raw data.",
                )
            )
        if flows.volatility is None:
            statuses.append(
                SourceStatus(
                    source="analytics-service",
                    capability="flow-volatility",
                    status="NOT_IMPLEMENTED",
                    reason="No owner aggregate supports this calculation without raw data.",
                )
            )
        customer = payloads.get("customer-service") or {}
        portfolio_payload = payloads.get("portfolio-service")
        if portfolio_payload is None:
            portfolio: dict[str, Any] = {}
        elif isinstance(portfolio_payload, dict):
            portfolio = portfolio_payload
        else:
            raise Problem(
                502, "DEPENDENCY_INVALID_RESPONSE", "Portfolio response must be an object."
            )

        raw_model = portfolio.get("model")
        if raw_model is None:
            model: dict[str, Any] = {}
        elif isinstance(raw_model, dict):
            model = raw_model
        else:
            raise Problem(
                502, "DEPENDENCY_INVALID_RESPONSE", "Portfolio model metadata must be an object."
            )
        for field in ("featureSetVersion", "modelVersion", "trainingDatasetVersion"):
            value = model.get(field)
            if value is not None and not isinstance(value, str):
                raise Problem(
                    502,
                    "DEPENDENCY_INVALID_RESPONSE",
                    "Portfolio model metadata contains an invalid field type.",
                )

        raw_combination = portfolio.get("combination")
        if raw_combination is None:
            combination: dict[str, Any] = {}
        elif isinstance(raw_combination, dict) and raw_combination:
            combination = raw_combination
        else:
            raise Problem(
                502,
                "DEPENDENCY_INVALID_RESPONSE",
                "Portfolio governance metadata must be a non-empty object.",
            )
        if combination:
            rules_weight = combination.get("rulesWeight")
            ml_weight = combination.get("mlWeight")
            if not _is_json_number(rules_weight) or not _is_json_number(ml_weight):
                raise Problem(
                    502,
                    "DEPENDENCY_INVALID_RESPONSE",
                    "Portfolio governance weights must be JSON numbers.",
                )
            if (
                combination.get("method") != "RULES_ONLY"
                or combination.get("mlObservationMode") != "POC_SHADOW"
                or float(rules_weight) != 1.0
                or float(ml_weight) != 0.0
            ):
                raise Problem(
                    502,
                    "DEPENDENCY_INVALID_RESPONSE",
                    "Portfolio governance invariants failed.",
                )
        if not combination:
            statuses.append(
                SourceStatus(
                    source="portfolio-service",
                    capability="rules-only-commercial-projection",
                    status="UNAVAILABLE",
                    reason="RULES_ONLY metadata was not available for this company.",
                )
            )
        statuses.extend(
            [
                SourceStatus(
                    source="signal-service",
                    capability="signal-lifecycle-point-in-time",
                    status="NOT_IMPLEMENTED",
                    reason=(
                        "Signal status is omitted because no historical lifecycle contract exists."
                    ),
                ),
                SourceStatus(
                    source="opportunity-service",
                    capability="opportunity-lifecycle-point-in-time",
                    status="NOT_IMPLEMENTED",
                    reason=(
                        "Opportunity status is omitted because no historical lifecycle "
                        "contract exists."
                    ),
                ),
            ]
        )
        summary = CompanySummary(
            companyId=company_id,
            legalName=customer.get("legalName"),
            sector=customer.get("sector"),
            segment=customer.get("segment"),
            status=customer.get("status"),
            portfolioId=portfolio_id,
            fundId=fund_id,
            visibility=visibility_projection(customer),
            cashPosition=cash,
            flowSummary=flows,
            signals=signal_projection(payloads.get("signal-service"), as_of=as_of),
            opportunities=opportunity_projection(payloads.get("opportunity-service"), as_of=as_of),
            metrics=[metric_projection(row) for row in rows],
        )
        calculation_versions = {
            str(row["calculationVersion"]) for row in rows if row.get("calculationVersion")
        }
        if len(calculation_versions) > 1:
            raise Problem(
                502, "DEPENDENCY_INVALID_RESPONSE", "Analytics versions are inconsistent."
            )
        return (
            summary,
            statuses,
            model.get("featureSetVersion"),
            model.get("modelVersion"),
            model.get("trainingDatasetVersion"),
            bool(combination),
        )


__all__ = [
    "FinancialIntelligenceComposer",
    "OwnerClients",
    "cash_position",
    "flow_summary",
    "opportunity_projection",
    "signal_projection",
]
