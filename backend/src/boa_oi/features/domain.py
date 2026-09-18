from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Mapping, Sequence

FEATURE_SET_VERSION: Final = "sales-features-v2"
FEATURE_ORDER: Final[tuple[str, ...]] = (
    "cash_inflow_growth_90d",
    "supplier_payment_growth_90d",
    "international_activity_ratio_90d",
    "balance_strength_90d",
    "activity_density_90d",
    "analytics_coverage_90d",
    "customer_tenure_ratio",
    "segment_medium",
    "confirmed_signal_ratio",
    "published_rule_match_strength",
)


def _bounded(value: float, lower: float, upper: float) -> float:
    if not math.isfinite(value):
        return lower
    return min(upper, max(lower, value))


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def feature_checksum(
    *,
    customer_id: str,
    as_of: date,
    feature_set_version: str,
    values: Mapping[str, float],
    sources: Sequence[Mapping[str, Any]],
) -> str:
    """Hash the complete, ordered feature lineage using a canonical JSON representation."""
    payload = {
        "asOf": as_of.isoformat(),
        "customerId": customer_id,
        "featureSetVersion": feature_set_version,
        "sources": list(sources),
        "values": {name: values[name] for name in FEATURE_ORDER},
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CustomerProfile:
    customer_id: str
    segment_code: str
    incorporated_on: date


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    customer_id: str
    as_of: date
    window_days: int
    calculation_version: str
    values: Mapping[str, Mapping[str, Any]]
    input_watermark: str


@dataclass(frozen=True, slots=True)
class CommercialIntelligenceSnapshot:
    confirmed_signal_ratio: float
    published_rule_match_strength: float
    signal_references: tuple[str, ...] = ()
    active_rule_versions: tuple[str, ...] = ()
    matched_rule_versions: tuple[str, ...] = ()
    rule_engine_version: str = "rule-engine-0.1.0"


@dataclass(frozen=True, slots=True)
class FeatureVector:
    customer_id: str
    as_of: date
    feature_set_version: str
    values: dict[str, float]
    sources: tuple[dict[str, Any], ...]
    checksum: str

    def __post_init__(self) -> None:
        if tuple(self.values) != FEATURE_ORDER:
            raise ValueError("feature values must follow the declared feature order")
        if len(self.checksum) != 64:
            raise ValueError("feature checksum must be SHA-256")


class FeatureBuilder:
    """Pure feature builder whose only inputs are Analytics snapshots and customer profiles."""

    def __init__(self, feature_set_version: str = FEATURE_SET_VERSION) -> None:
        if not feature_set_version.strip():
            raise ValueError("feature set version is required")
        self.feature_set_version = feature_set_version

    @staticmethod
    def _metric(
        snapshot: AnalyticsSnapshot, metric: str, field: str, default: float = 0.0
    ) -> float:
        return _number(snapshot.values.get(metric, {}).get(field), default)

    def build(
        self,
        profile: CustomerProfile,
        snapshots: Sequence[AnalyticsSnapshot],
        as_of: date,
        intelligence: CommercialIntelligenceSnapshot | None = None,
    ) -> FeatureVector:
        eligible = [
            item
            for item in snapshots
            if item.customer_id == profile.customer_id
            and item.window_days == 90
            and item.as_of <= as_of
        ]
        if not eligible:
            raise ValueError("a 90-day Analytics snapshot is required")
        snapshot = max(eligible, key=lambda item: (item.as_of, item.calculation_version))

        inflow = self._metric(snapshot, "inflow_amount", "currentValue")
        outflow = self._metric(snapshot, "outflow_amount", "currentValue")
        international = self._metric(snapshot, "international_flow_amount", "currentValue")
        average_balance = self._metric(snapshot, "average_balance", "currentValue")
        activity = self._metric(snapshot, "transaction_count", "currentValue")
        coverage_items = [
            self._metric(snapshot, metric, "dataCoverage")
            for metric in (
                "inflow_amount",
                "supplier_payment_amount",
                "international_flow_amount",
                "average_balance",
                "transaction_count",
            )
        ]
        tenure_years = max(0.0, (as_of - profile.incorporated_on).days / 365.2425)
        values = {
            "cash_inflow_growth_90d": _bounded(
                self._metric(snapshot, "inflow_amount", "growthRate"), -1.0, 3.0
            ),
            "supplier_payment_growth_90d": _bounded(
                self._metric(snapshot, "supplier_payment_amount", "growthRate"), -1.0, 3.0
            ),
            "international_activity_ratio_90d": _bounded(
                international / max(1.0, inflow + outflow), 0.0, 1.0
            ),
            "balance_strength_90d": _bounded(
                math.log1p(max(0.0, average_balance)) / math.log1p(10_000_000.0),
                0.0,
                2.0,
            ),
            "activity_density_90d": _bounded(
                math.log1p(max(0.0, activity)) / math.log1p(2_000.0), 0.0, 1.5
            ),
            "analytics_coverage_90d": _bounded(
                sum(coverage_items) / len(coverage_items), 0.0, 1.0
            ),
            "customer_tenure_ratio": _bounded(tenure_years / 15.0, 0.0, 2.0),
            "segment_medium": float(profile.segment_code.upper() == "MEDIUM"),
            "confirmed_signal_ratio": _bounded(
                intelligence.confirmed_signal_ratio if intelligence else 0.0,
                0.0,
                1.0,
            ),
            "published_rule_match_strength": _bounded(
                intelligence.published_rule_match_strength if intelligence else 0.0,
                0.0,
                1.0,
            ),
        }
        rounded = {name: round(values[name], 10) for name in FEATURE_ORDER}
        sources = (
            {
                "sourceType": "ANALYTICS_SNAPSHOT",
                "asOf": snapshot.as_of.isoformat(),
                "windowDays": snapshot.window_days,
                "calculationVersion": snapshot.calculation_version,
                "inputWatermark": snapshot.input_watermark,
            },
            {
                "sourceType": "CUSTOMER_PROFILE",
                "segment": profile.segment_code.upper(),
                "incorporatedOn": profile.incorporated_on.isoformat(),
            },
            {
                "sourceType": "SIGNAL_SERVICE",
                "signalReferences": list(intelligence.signal_references) if intelligence else [],
                "confirmedSignalRatio": (
                    intelligence.confirmed_signal_ratio if intelligence else 0.0
                ),
            },
            {
                "sourceType": "RULE_STUDIO",
                "engineVersion": (
                    intelligence.rule_engine_version if intelligence else "rule-engine-0.1.0"
                ),
                "activeRuleVersions": (
                    list(intelligence.active_rule_versions) if intelligence else []
                ),
                "matchedRuleVersions": (
                    list(intelligence.matched_rule_versions) if intelligence else []
                ),
            },
        )
        checksum = feature_checksum(
            customer_id=profile.customer_id,
            as_of=as_of,
            feature_set_version=self.feature_set_version,
            values=rounded,
            sources=sources,
        )
        return FeatureVector(
            customer_id=profile.customer_id,
            as_of=as_of,
            feature_set_version=self.feature_set_version,
            values=rounded,
            sources=sources,
            checksum=checksum,
        )


__all__ = [
    "FEATURE_ORDER",
    "FEATURE_SET_VERSION",
    "AnalyticsSnapshot",
    "CommercialIntelligenceSnapshot",
    "CustomerProfile",
    "FeatureBuilder",
    "FeatureVector",
    "feature_checksum",
]
