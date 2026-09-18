from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class PriorityComponent:
    name: str
    weight: float
    normalized_value: float
    contribution: float


@dataclass(frozen=True, slots=True)
class PriorityResult:
    score: float
    level: Literal["P1", "P2", "P3", "P4"]
    components: tuple[PriorityComponent, ...]


class PriorityScoreCalculator:
    def __init__(
        self,
        weights: Mapping[str, float],
        *,
        p1: float = 80,
        p2: float = 60,
        p3: float = 40,
    ) -> None:
        if not weights or any(weight < 0 for weight in weights.values()):
            raise ValueError("priority weights must be non-negative")
        if abs(sum(weights.values()) - 1.0) > 1e-9:
            raise ValueError("priority weights must sum to one")
        if not p1 > p2 > p3:
            raise ValueError("priority thresholds are invalid")
        self.weights = dict(weights)
        self.thresholds = (p1, p2, p3)

    def calculate(
        self,
        factors: Mapping[str, float | None],
        *,
        confidence_level: Literal["LOW", "MEDIUM", "HIGH"] = "HIGH",
    ) -> PriorityResult:
        components: list[PriorityComponent] = []
        score = 0.0
        for name, weight in self.weights.items():
            raw = factors.get(name)
            if raw is not None and not math.isfinite(raw):
                raise ValueError(f"non-finite priority factor: {name}")
            normalized = (
                0.5
                if raw is None and name == "relationship_context"
                else 0.0
                if raw is None
                else min(1.0, max(0.0, raw))
            )
            contribution = normalized * weight * 100
            score += contribution
            components.append(PriorityComponent(name, weight, normalized, round(contribution, 6)))
        score = round(min(100.0, max(0.0, score)), 6)
        p1, p2, p3 = self.thresholds
        level: Literal["P1", "P2", "P3", "P4"] = (
            "P1" if score >= p1 else "P2" if score >= p2 else "P3" if score >= p3 else "P4"
        )
        if confidence_level == "LOW" and level in {"P1", "P2"}:
            level = "P3"
        return PriorityResult(score=score, level=level, components=tuple(components))
