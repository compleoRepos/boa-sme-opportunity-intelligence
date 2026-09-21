from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Final, Iterable, Literal

BankingRelationship = Literal["EXCLUSIVE", "PRIMARY", "SECONDARY", "UNKNOWN"]
VisibilityLevel = Literal["HIGH", "PARTIAL", "LOW", "UNKNOWN"]
VisibilityMethod = Literal["DECLARED", "TURNOVER_RATIO", "TRANSACTION_FINGERPRINTS", "NONE"]
VisibilitySensitivity = Literal["ROBUST", "SENSITIVE"]

HYPOTHESIS_LABEL: Final = "HYPOTHÈSE À VALIDER AVEC BOA"
VISIBILITY_THRESHOLDS: Final[dict[str, float | int | str]] = {
    "high_share": 0.70,
    "partial_share": 0.30,
    "fingerprints_90d": 2,
    "partial_penalty_points": -10,
    "low_penalty_points": -25,
    "unknown_penalty_points": -5,
    "domiciliation_cooldown_days": 180,
    "status": HYPOTHESIS_LABEL,
}

SIGNAL_VISIBILITY_SENSITIVITY: Final[dict[str, VisibilitySensitivity]] = {
    "INFLOW_GROWTH": "ROBUST",
    "SUPPLIER_PAYMENT_GROWTH": "ROBUST",
    "TRANSACTION_VOLUME_GROWTH": "ROBUST",
    "INTERNATIONAL_FLOW_GROWTH": "ROBUST",
    "BALANCE_SURPLUS": "SENSITIVE",
    "CREDIT_UTILIZATION_INCREASE": "SENSITIVE",
}

OPPORTUNITY_VISIBILITY_SENSITIVITY: Final[dict[str, VisibilitySensitivity]] = {
    "INVESTMENT_FINANCING": "ROBUST",
    "TRADE_FINANCE": "ROBUST",
    "CASH_INVESTMENT": "SENSITIVE",
    "FINANCIAL_STRESS_SIGNAL": "SENSITIVE",
    "FLOW_DOMICILIATION": "ROBUST",
}


def _normalize_name(value: str) -> tuple[str, ...]:
    normalized = re.sub(r"[^A-Z0-9 ]+", " ", value.upper())
    ignored = {"SA", "SARL", "SAS", "SNC", "STE", "SOCIETE", "COMPANY", "ENTREPRISE"}
    return tuple(word for word in normalized.split() if len(word) >= 3 and word not in ignored)


def is_inter_bank_self_transfer(
    *,
    legal_name: str,
    transaction_type: str,
    counterparty_name: str | None = None,
    remittance_information: str | None = None,
    externally_domiciled: bool = False,
) -> bool:
    """Classify only explicit, explainable self-transfer fingerprints.

    The rule is deliberately conservative: an external-domiliation flag supplied by the
    transaction contract is sufficient; otherwise a transfer must carry at least one
    meaningful token from the customer's legal name in its counterparty or remittance text.
    """

    if externally_domiciled:
        return True
    if transaction_type.upper() not in {"TRANSFER", "WIRE", "VIREMENT"}:
        return False
    evidence_text = " ".join(filter(None, (counterparty_name, remittance_information))).upper()
    return any(token in evidence_text for token in _normalize_name(legal_name))


@dataclass(frozen=True, slots=True)
class VisibilityTransaction:
    value_date: date
    direction: str
    amount: Decimal
    category: str
    status: str = "BOOKED"


@dataclass(frozen=True, slots=True)
class FlowVisibilityEstimate:
    level: VisibilityLevel
    estimated_share: float | None
    method: VisibilityMethod
    as_of: date
    evidence: tuple[dict[str, object], ...]
    fingerprint_count_90d: int
    fingerprint_previous_90d: int
    categorization_coverage: float

    @property
    def fingerprint_growth_90d(self) -> int:
        return self.fingerprint_count_90d - self.fingerprint_previous_90d

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "estimatedShare": self.estimated_share,
            "method": self.method,
            "asOf": self.as_of.isoformat(),
            "evidence": list(self.evidence),
            "fingerprintCount90d": self.fingerprint_count_90d,
            "fingerprintPrevious90d": self.fingerprint_previous_90d,
            "fingerprintGrowth90d": self.fingerprint_growth_90d,
            "categorizationCoverage": self.categorization_coverage,
        }


def estimate_flow_visibility(
    *,
    as_of: date,
    banking_relationship: BankingRelationship | None,
    relationship_as_of: datetime | None,
    declared_turnover: Decimal | None,
    turnover_as_of: date | None,
    transactions: Iterable[VisibilityTransaction],
    high_share: float = 0.70,
    partial_share: float = 0.30,
    fingerprint_threshold: int = 2,
) -> FlowVisibilityEstimate:
    rows = tuple(
        item for item in transactions if item.value_date <= as_of and item.status == "BOOKED"
    )
    categorized = sum(bool(item.category and item.category != "OTHER") for item in rows)
    coverage = categorized / len(rows) if rows else 0.0
    current_start = as_of - timedelta(days=89)
    previous_start = as_of - timedelta(days=179)
    fingerprints = tuple(item for item in rows if item.category == "INTER_BANK_SELF_TRANSFER")
    current_fingerprints = sum(current_start <= item.value_date <= as_of for item in fingerprints)
    previous_fingerprints = sum(
        previous_start <= item.value_date < current_start for item in fingerprints
    )

    relationship = banking_relationship or "UNKNOWN"
    declared_map: dict[str, VisibilityLevel] = {
        "EXCLUSIVE": "HIGH",
        "PRIMARY": "PARTIAL",
        "SECONDARY": "LOW",
    }
    declared_date = (
        relationship_as_of.astimezone(timezone.utc).date()
        if relationship_as_of and relationship_as_of.tzinfo
        else relationship_as_of.date()
        if relationship_as_of
        else as_of
    )
    if relationship in declared_map and declared_date <= as_of:
        return FlowVisibilityEstimate(
            declared_map[relationship],
            None,
            "DECLARED",
            as_of,
            (
                {
                    "fact": "BANKING_RELATIONSHIP_DECLARED",
                    "value": relationship,
                    "observedAt": declared_date.isoformat(),
                },
            ),
            current_fingerprints,
            previous_fingerprints,
            coverage,
        )

    if (
        declared_turnover is not None
        and declared_turnover > 0
        and (turnover_as_of is None or turnover_as_of <= as_of)
    ):
        start = as_of - timedelta(days=364)
        inflows = sum(
            (
                item.amount
                for item in rows
                if start <= item.value_date <= as_of
                and item.direction == "CREDIT"
                and item.category != "INTER_BANK_SELF_TRANSFER"
            ),
            Decimal(0),
        )
        share = min(Decimal(1), max(Decimal(0), inflows / declared_turnover))
        numeric_share = round(float(share), 6)
        level: VisibilityLevel = (
            "HIGH"
            if numeric_share >= high_share
            else "PARTIAL"
            if numeric_share >= partial_share
            else "LOW"
        )
        return FlowVisibilityEstimate(
            level,
            numeric_share,
            "TURNOVER_RATIO",
            as_of,
            (
                {
                    "fact": "BOA_INFLOW_12M",
                    "value": float(inflows),
                    "observedAt": as_of.isoformat(),
                },
                {
                    "fact": "DECLARED_TURNOVER",
                    "value": float(declared_turnover),
                    "observedAt": (turnover_as_of or as_of).isoformat(),
                },
                {
                    "fact": "VISIBILITY_THRESHOLDS",
                    "value": {"high": high_share, "partial": partial_share},
                    "status": HYPOTHESIS_LABEL,
                    "observedAt": as_of.isoformat(),
                },
            ),
            current_fingerprints,
            previous_fingerprints,
            coverage,
        )

    level = "PARTIAL" if current_fingerprints >= fingerprint_threshold else "UNKNOWN"
    evidence: tuple[dict[str, object], ...] = (
        {
            "fact": "INTER_BANK_SELF_TRANSFER_90D",
            "value": current_fingerprints,
            "observedAt": as_of.isoformat(),
            "threshold": fingerprint_threshold,
            "status": HYPOTHESIS_LABEL,
        },
        {
            "fact": "TRANSACTION_CATEGORIZATION_COVERAGE",
            "value": round(coverage, 6),
            "observedAt": as_of.isoformat(),
        },
    )
    return FlowVisibilityEstimate(
        level,
        None,
        "TRANSACTION_FINGERPRINTS" if current_fingerprints else "NONE",
        as_of,
        evidence,
        current_fingerprints,
        previous_fingerprints,
        coverage,
    )


def visibility_penalty_points(
    level: VisibilityLevel,
    *,
    partial: int = -10,
    low: int = -25,
    unknown: int = -5,
) -> int:
    return {"HIGH": 0, "PARTIAL": partial, "LOW": low, "UNKNOWN": unknown}[level]


def visibility_explanation(level: VisibilityLevel) -> str:
    if level == "PARTIAL":
        return "Visibilité des flux partielle : signal de niveau pondéré"
    if level == "LOW":
        return "Visibilité des flux faible : signal de niveau pondéré"
    if level == "UNKNOWN":
        return "Visibilité des flux inconnue : signal de niveau pondéré"
    return "Visibilité des flux forte : aucune pondération"


__all__ = [
    "HYPOTHESIS_LABEL",
    "OPPORTUNITY_VISIBILITY_SENSITIVITY",
    "SIGNAL_VISIBILITY_SENSITIVITY",
    "VISIBILITY_THRESHOLDS",
    "BankingRelationship",
    "FlowVisibilityEstimate",
    "VisibilityTransaction",
    "estimate_flow_visibility",
    "is_inter_bank_self_transfer",
    "visibility_explanation",
    "visibility_penalty_points",
]
