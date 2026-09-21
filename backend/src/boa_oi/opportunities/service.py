from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal

from boa_oi.confidence import ConfidenceComponent, ConfidenceResult, ConfidenceScoreCalculator
from boa_oi.priority import PriorityScoreCalculator
from boa_oi.technical.config import RuleSetConfig
from boa_oi.technical.ids import deterministic_uuid
from boa_oi.visibility import visibility_explanation, visibility_penalty_points

from .domain import OpportunityCandidate, OpportunityContext
from .strategies import RuleBasedOpportunityStrategy, StatisticalOpportunityStrategy


class OpportunityEngine:
    def __init__(self, config: RuleSetConfig) -> None:
        self.config = config
        self.rule_strategy = RuleBasedOpportunityStrategy()
        self.statistical_guard = StatisticalOpportunityStrategy()
        self.priority_calculator = PriorityScoreCalculator(
            config.priority.weights,
            p1=config.priority.p1,
            p2=config.priority.p2,
            p3=config.priority.p3,
        )

    @staticmethod
    def _default_confidence(context: OpportunityContext, rule_code: str) -> dict[str, float]:
        product_gap = (
            1.0
            if any(
                bool(context.facts.get(key))
                for key in ("trade_finance_gap", "no_recent_investment_financing")
            )
            else 0.7
        )
        return {
            "signal_strength": 0.85,
            "persistence": min(1.0, float(context.facts.get("persistence_score", 0.8))),
            "baseline_separation": 1.0 if context.seasonality_adjusted else 0.0,
            "product_gap": product_gap,
            "recency": 1.0,
            "data_quality": context.data_coverage,
            "corroboration": 0.8,
        }

    def evaluate(self, context: OpportunityContext) -> tuple[OpportunityCandidate, ...]:
        candidates: list[OpportunityCandidate] = []
        for opportunity_type, rule in sorted(self.config.opportunity_rules.items()):
            if opportunity_type == "CASH_INVESTMENT" and context.flow_visibility_level == "LOW":
                continue
            if not rule.enabled or not self.statistical_guard.allows(context, rule):
                continue
            matched, evidence = self.rule_strategy.evaluate(context, rule)
            if not matched:
                continue
            confidence_calculator = ConfidenceScoreCalculator(
                rule.confidence_weights,
                high=self.config.confidence_levels.high,
                medium=self.config.confidence_levels.medium,
            )
            confidence = confidence_calculator.calculate(
                context.confidence_factors or self._default_confidence(context, opportunity_type)
            )
            if rule.visibility_sensitivity == "SENSITIVE":
                flow_rule = self.config.opportunity_rules.get("FLOW_DOMICILIATION")
                visibility_policy = flow_rule.visibility_policy if flow_rule else {}
                penalty = visibility_penalty_points(
                    context.flow_visibility_level,
                    partial=int(visibility_policy.get("partialPenaltyPoints", -10)),
                    low=int(visibility_policy.get("lowPenaltyPoints", -25)),
                    unknown=int(visibility_policy.get("unknownPenaltyPoints", -5)),
                )
                adjusted_score = round(max(0.0, confidence.score + penalty / 100), 6)
                adjusted_level: Literal["LOW", "MEDIUM", "HIGH"] = (
                    "HIGH"
                    if adjusted_score >= self.config.confidence_levels.high
                    else "MEDIUM"
                    if adjusted_score >= self.config.confidence_levels.medium
                    else "LOW"
                )
                confidence = ConfidenceResult(
                    score=adjusted_score,
                    level=adjusted_level,
                    components=(
                        *confidence.components,
                        ConfidenceComponent(
                            name="visibility",
                            weight=abs(float(penalty)),
                            raw_value=float(penalty),
                            normalized_value=1.0 if penalty == 0 else 0.0,
                            points=float(penalty),
                            reason=visibility_explanation(context.flow_visibility_level),
                        ),
                    ),
                    maximum_points=confidence.maximum_points,
                )
            priority_factors: dict[str, float | None] = dict(rule.priority_defaults)
            priority_factors.update(context.priority_factors)
            priority_factors["confidence"] = confidence.score
            priority = self.priority_calculator.calculate(
                priority_factors, confidence_level=confidence.level
            )
            opportunity_id = str(
                deterministic_uuid(
                    "opportunity",
                    context.customer_id,
                    opportunity_type,
                    context.as_of_date,
                    self.config.engine_version,
                    rule.version,
                )
            )
            generated_at = datetime.combine(
                context.as_of_date, datetime.min.time(), tzinfo=timezone.utc
            ).isoformat()
            why = tuple(
                f"{item.label}: observed={item.observed}, condition={item.operator} {item.expected}"
                for item in evidence
                if item.passed
            )
            candidates.append(
                OpportunityCandidate(
                    opportunity_id=opportunity_id,
                    customer_id=context.customer_id,
                    opportunity_type=opportunity_type,
                    horizon=rule.horizon,
                    confidence=confidence.score,
                    confidence_level=confidence.level,
                    confidence_components=tuple(
                        asdict(component) for component in confidence.components
                    ),
                    priority_score=priority.score,
                    priority_level=priority.level,
                    priority_components=tuple(
                        asdict(component) for component in priority.components
                    ),
                    why=why,
                    what=rule.what,
                    when=rule.when,
                    recommended_products=rule.recommended_product_codes,
                    recommendation_nature=(
                        "WIN_BACK"
                        if context.flow_visibility_level in {"PARTIAL", "LOW"}
                        else "NEED_DISCOVERY"
                    ),
                    evidence=evidence,
                    as_of_date=context.as_of_date,
                    generated_at=generated_at,
                    engine_version=self.config.engine_version,
                    rule_version=rule.version,
                    rule_set_version=self.config.rule_set_version,
                    lifecycle_policy=rule.lifecycle.model_dump(mode="python"),
                )
            )
        return tuple(candidates)
