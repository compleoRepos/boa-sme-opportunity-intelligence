from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from operator import ge, gt, le, lt
from typing import Literal

from boa_oi.technical.config import SignalRuleConfig
from boa_oi.technical.ids import deterministic_uuid

from .domain import MetricObservation, Signal

OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "gt": gt,
    "gte": ge,
    "lt": lt,
    "lte": le,
}


class SignalDetector:
    def __init__(self, rules: Mapping[str, SignalRuleConfig], *, period: str = "90D") -> None:
        self.rules = dict(rules)
        self.period = period

    @staticmethod
    def _severity(value: float, threshold: float) -> Literal["LOW", "MEDIUM", "HIGH"]:
        denominator = max(abs(threshold), 1e-9)
        margin = abs(value - threshold) / denominator
        if margin <= 0.10:
            return "LOW"
        if margin <= 0.50:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _value(observation: MetricObservation, field: str) -> float | None:
        return getattr(observation, field)

    def detect(
        self,
        customer_id: str,
        observations: Mapping[str, MetricObservation],
        as_of_date: date,
    ) -> tuple[Signal, ...]:
        detected: list[Signal] = []
        for signal_type, rule in sorted(self.rules.items()):
            if not rule.enabled:
                continue
            observation = observations.get(rule.metric)
            if observation is None or observation.quality_status in {
                "DATA_INVALID",
                "INSUFFICIENT_HISTORY",
            }:
                continue
            value = self._value(observation, rule.value_field)
            if value is None or observation.sample_size < rule.minimum_sample_size:
                continue
            if not observation.seasonality_adjusted or not OPERATORS[rule.operator](
                value, rule.threshold
            ):
                continue
            denominator = max(abs(rule.threshold), 1e-9)
            strong = abs(value - rule.threshold) / denominator > rule.strong_evidence_margin
            confirmed = (
                not rule.require_confirmation or observation.confirmation_count >= 2 or strong
            )
            signal_id = str(
                deterministic_uuid(
                    "signal",
                    customer_id,
                    signal_type,
                    self.period,
                    as_of_date,
                    rule.version,
                )
            )
            evidence = (
                f"{observation.metric} observed={value:.6f}, "
                f"threshold {rule.operator} {rule.threshold:.6f}",
                f"sample_size={observation.sample_size}, coverage={observation.data_coverage:.2%}",
                f"historical_baseline={observation.historical_baseline}",
            )
            detected.append(
                Signal(
                    signal_id=signal_id,
                    customer_id=customer_id,
                    signal_type=signal_type,
                    severity=self._severity(value, rule.threshold),
                    status="CONFIRMED" if confirmed else "OBSERVED",
                    value=value,
                    threshold=rule.threshold,
                    period=self.period,
                    as_of_date=as_of_date,
                    evidence=evidence,
                    metric_reference=observation.metric,
                    rule_version=rule.version,
                )
            )
        return tuple(detected)
