from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ConfidenceComponent:
    name: str
    weight: float
    raw_value: float | None
    normalized_value: float
    points: float
    reason: str


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    score: float
    level: Literal["LOW", "MEDIUM", "HIGH"]
    components: tuple[ConfidenceComponent, ...]
    maximum_points: float


class ConfidenceScoreCalculator:
    def __init__(
        self, weights: Mapping[str, float], *, high: float = 0.75, medium: float = 0.50
    ) -> None:
        if (
            not weights
            or any(weight < 0 for weight in weights.values())
            or sum(weights.values()) <= 0
        ):
            raise ValueError("weights must contain a positive total")
        if not 0 <= medium < high <= 1:
            raise ValueError("confidence thresholds are invalid")
        self.weights = dict(weights)
        self.high = high
        self.medium = medium

    def calculate(
        self,
        factors: Mapping[str, float | None],
        *,
        reasons: Mapping[str, str] | None = None,
        score_cap: float = 1.0,
    ) -> ConfidenceResult:
        if not 0 <= score_cap <= 1:
            raise ValueError("score cap must be in [0, 1]")
        total_weight = sum(self.weights.values())
        components: list[ConfidenceComponent] = []
        earned = 0.0
        for name, weight in self.weights.items():
            raw = factors.get(name)
            if raw is not None and not math.isfinite(raw):
                raise ValueError(f"non-finite factor: {name}")
            normalized = 0.0 if raw is None else min(1.0, max(0.0, raw))
            points = weight * normalized
            earned += points
            components.append(
                ConfidenceComponent(
                    name=name,
                    weight=weight,
                    raw_value=raw,
                    normalized_value=normalized,
                    points=round(points, 10),
                    reason=(reasons or {}).get(
                        name,
                        "missing evidence" if raw is None else "configured evidence factor",
                    ),
                )
            )
        score = min(score_cap, max(0.0, earned / total_weight))
        score = round(score, 6)
        level: Literal["LOW", "MEDIUM", "HIGH"] = (
            "HIGH" if score >= self.high else "MEDIUM" if score >= self.medium else "LOW"
        )
        return ConfidenceResult(
            score=score,
            level=level,
            components=tuple(components),
            maximum_points=total_weight,
        )
