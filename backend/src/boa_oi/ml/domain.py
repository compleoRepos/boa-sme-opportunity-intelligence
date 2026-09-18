from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final, Literal, Mapping

SCORE_TYPE: Final = "SALES_PROPENSITY"
ModelStatus = Literal["CHALLENGER", "ACTIVE", "RETIRED"]


@dataclass(frozen=True, slots=True)
class LogisticModel:
    model_version: str
    feature_set_version: str
    coefficients: Mapping[str, float]
    intercept: float
    feature_order: tuple[str, ...]
    threshold: float
    validation_metrics: Mapping[str, Any]
    status: ModelStatus

    def __post_init__(self) -> None:
        if not self.model_version or not self.feature_set_version:
            raise ValueError("model and feature versions are required")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between zero and one")
        if not math.isfinite(self.intercept):
            raise ValueError("intercept must be finite")
        if not self.feature_order or len(set(self.feature_order)) != len(self.feature_order):
            raise ValueError("feature order must contain unique names")
        if set(self.coefficients) != set(self.feature_order):
            raise ValueError("coefficients must exactly match the feature order")
        if any(not math.isfinite(value) for value in self.coefficients.values()):
            raise ValueError("all coefficients must be finite")
        if self.status not in {"CHALLENGER", "ACTIVE", "RETIRED"}:
            raise ValueError("unsupported model status")


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    feature: str
    value: float
    coefficient: float
    contribution: float
    direction: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]


@dataclass(frozen=True, slots=True)
class PropensityScore:
    score_type: Literal["SALES_PROPENSITY"]
    propensity: float
    threshold: float
    above_threshold: bool
    calibration: str
    segment: str
    model_version: str
    feature_version: str
    feature_checksum: str
    contributions: tuple[FeatureContribution, ...]
    top_factors: tuple[FeatureContribution, ...]


def stable_sigmoid(logit: float) -> float:
    """Numerically stable logistic link implemented with the Python standard library."""
    if logit >= 0.0:
        return 1.0 / (1.0 + math.exp(-logit))
    exp_value = math.exp(logit)
    return exp_value / (1.0 + exp_value)


def calibration_band(score: float) -> str:
    if score < 0.35:
        return "LOW"
    if score < 0.65:
        return "MEDIUM"
    return "HIGH"


class LogisticScorer:
    """CPU-only inference for a transparent JSON-coefficient logistic model."""

    def score(
        self,
        model: LogisticModel,
        features: Mapping[str, float],
        *,
        feature_version: str,
        feature_checksum: str,
        segment: str,
        top_n: int = 3,
    ) -> PropensityScore:
        if feature_version != model.feature_set_version:
            raise ValueError("feature set version is incompatible with the model")
        if top_n < 1:
            raise ValueError("at least one top factor is required")
        missing = [name for name in model.feature_order if name not in features]
        unexpected = sorted(set(features) - set(model.feature_order))
        if missing or unexpected:
            raise ValueError(f"invalid feature vector: missing={missing}, unexpected={unexpected}")

        contributions: list[FeatureContribution] = []
        logit = model.intercept
        for name in model.feature_order:
            value = float(features[name])
            if not math.isfinite(value):
                raise ValueError(f"feature {name} must be finite")
            coefficient = float(model.coefficients[name])
            contribution = coefficient * value
            logit += contribution
            direction: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
            if contribution > 0.0:
                direction = "POSITIVE"
            elif contribution < 0.0:
                direction = "NEGATIVE"
            else:
                direction = "NEUTRAL"
            contributions.append(
                FeatureContribution(
                    feature=name,
                    value=value,
                    coefficient=coefficient,
                    contribution=contribution,
                    direction=direction,
                )
            )
        propensity = stable_sigmoid(logit)
        top_factors = tuple(
            sorted(
                contributions,
                key=lambda item: (-abs(item.contribution), item.feature),
            )[: min(top_n, len(contributions))]
        )
        return PropensityScore(
            score_type=SCORE_TYPE,
            propensity=propensity,
            threshold=model.threshold,
            above_threshold=propensity >= model.threshold,
            calibration=calibration_band(propensity),
            segment=segment.upper(),
            model_version=model.model_version,
            feature_version=feature_version,
            feature_checksum=feature_checksum,
            contributions=tuple(contributions),
            top_factors=top_factors,
        )


__all__ = [
    "SCORE_TYPE",
    "FeatureContribution",
    "LogisticModel",
    "LogisticScorer",
    "ModelStatus",
    "PropensityScore",
    "calibration_band",
    "stable_sigmoid",
]
