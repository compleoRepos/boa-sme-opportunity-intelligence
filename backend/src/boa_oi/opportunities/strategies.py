from __future__ import annotations

from collections.abc import Callable
from operator import eq, ge, gt, le, lt, ne
from typing import Any, Protocol

from boa_oi.technical.config import ConditionConfig, OpportunityRuleConfig

from .domain import ConditionEvidence, OpportunityContext

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "gt": gt,
    "gte": ge,
    "lt": lt,
    "lte": le,
    "eq": eq,
    "neq": ne,
}


class OpportunityStrategy(Protocol):
    def evaluate(
        self, context: OpportunityContext, rule: OpportunityRuleConfig
    ) -> tuple[bool, tuple[ConditionEvidence, ...]]: ...


class StatisticalOpportunityStrategy:
    """Deterministic data-quality, persistence and anti-false-positive guard."""

    def allows(self, context: OpportunityContext, rule: OpportunityRuleConfig) -> bool:
        condition_flags = (
            context.facts.get(f"{condition.key}_seasonality_adjusted", True)
            for condition in (*rule.all_conditions, *rule.any_conditions)
        )
        return (
            context.data_quality == "VALID"
            and context.data_coverage >= rule.minimum_data_coverage
            and context.seasonality_adjusted
            and all(bool(flag) for flag in condition_flags)
            and not context.false_positive_flags
        )


class RuleBasedOpportunityStrategy:
    def _condition(
        self, context: OpportunityContext, condition: ConditionConfig
    ) -> ConditionEvidence:
        observed = context.facts.get(condition.key)
        passed = observed is not None and OPERATORS[condition.operator](observed, condition.value)
        return ConditionEvidence(
            key=condition.key,
            operator=condition.operator,
            expected=condition.value,
            observed=observed,
            passed=passed,
            label=condition.label,
        )

    def evaluate(
        self, context: OpportunityContext, rule: OpportunityRuleConfig
    ) -> tuple[bool, tuple[ConditionEvidence, ...]]:
        all_evidence = tuple(
            self._condition(context, condition) for condition in rule.all_conditions
        )
        any_evidence = tuple(
            self._condition(context, condition) for condition in rule.any_conditions
        )
        all_pass = all(item.passed for item in all_evidence)
        any_pass = not any_evidence or any(item.passed for item in any_evidence)
        return all_pass and any_pass, all_evidence + any_evidence


class MLOpportunityStrategy:
    """Explicit extension boundary; not active in the deterministic MVP."""

    def evaluate(
        self, context: OpportunityContext, rule: OpportunityRuleConfig
    ) -> tuple[bool, tuple[ConditionEvidence, ...]]:
        raise NotImplementedError("ML strategy is intentionally not enabled in the MVP")
