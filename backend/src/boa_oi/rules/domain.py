from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

ENGINE_VERSION = "rule-engine-0.1.0"

_OPERATOR_ALIASES = {
    ">": ">",
    "GREATER_THAN": ">",
    ">=": ">=",
    "GREATER_THAN_OR_EQUAL": ">=",
    "GREATER_THAN_OR_EQUALS": ">=",
    "<": "<",
    "LESS_THAN": "<",
    "<=": "<=",
    "LESS_THAN_OR_EQUAL": "<=",
    "LESS_THAN_OR_EQUALS": "<=",
    "=": "=",
    "==": "=",
    "EQUAL": "=",
    "EQUALS": "=",
    "!=": "!=",
    "NOT_EQUAL": "!=",
    "NOT_EQUALS": "!=",
    "BETWEEN": "BETWEEN",
    "IN": "IN",
    "NOT_IN": "NOT_IN",
    "INCREASE_BY": "INCREASE_BY",
    "DECREASE_BY": "DECREASE_BY",
    "PERSISTENT_FOR": "PERSISTENT_FOR",
}
SUPPORTED_OPERATORS = frozenset(_OPERATOR_ALIASES.values())
SUPPORTED_LOGIC = frozenset({"AND", "OR", "NOT"})


def canonical_operator(value: str) -> str:
    key = value.strip().upper().replace(" ", "_")
    try:
        return _OPERATOR_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported operator: {value}") from exc


def _token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("a numeric value is required")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("a numeric value is required") from exc
    if not number.is_finite():
        raise ValueError("a finite numeric value is required")
    return number


def _configured_number(value: Any, unit: str | None) -> Decimal:
    number = _decimal(value)
    if (unit or "").upper() in {"PERCENT", "PERCENTAGE", "%"} and abs(number) > 1:
        return number / Decimal(100)
    return number


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _equal(actual: Any, expected: Any, unit: str | None) -> bool:
    try:
        return _decimal(actual) == _configured_number(expected, unit)
    except ValueError:
        return actual == expected


def _ordered(actual: Any, expected: Any, operator: str, unit: str | None) -> bool:
    left = _decimal(actual)
    right = _configured_number(expected, unit)
    return {
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[operator]


def _current(metric: Any) -> Any:
    if not isinstance(metric, dict):
        return metric
    for key in ("actual", "value", "currentValue", "current_value", "growthRate", "growth_rate"):
        if key in metric and metric[key] is not None:
            return metric[key]
    return None


def _change(metric: Any, *, decrease: bool, unit: str | None) -> Decimal:
    if not isinstance(metric, dict):
        value = _decimal(metric)
        return -value if decrease else value
    current = _decimal(metric.get("currentValue", metric.get("current_value")))
    previous = _decimal(metric.get("previousPeriodValue", metric.get("previous_value")))
    delta = previous - current if decrease else current - previous
    if (unit or "").upper() in {"PERCENT", "PERCENTAGE", "%"}:
        if previous == 0:
            raise ValueError("percentage change is unavailable when the previous value is zero")
        return delta / abs(previous)
    return delta


def _history(metric: Any) -> list[Any]:
    if not isinstance(metric, dict):
        return []
    raw = metric.get("history", metric.get("observations", []))
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _persistent(metric: Any, expected: Any, unit: str | None) -> tuple[bool, Any, Any]:
    if isinstance(expected, dict):
        duration = expected.get("periods", expected.get("duration", expected.get("for")))
        if duration is None:
            raise ValueError("PERSISTENT_FOR requires a duration")
        nested_operator = canonical_operator(str(expected.get("operator", "=")))
        nested_value = expected.get("value", True)
        consecutive = 0
        for observed in reversed(_history(metric)):
            if _compare(observed, nested_operator, nested_value, unit)[0]:
                consecutive += 1
            else:
                break
        return consecutive >= int(duration), consecutive, int(duration)
    duration = int(_decimal(expected))
    if isinstance(metric, dict):
        supplied = metric.get("persistentFor", metric.get("persistent_for"))
        if supplied is not None:
            actual_duration = int(_decimal(supplied))
        else:
            actual_duration = 0
            for observed in reversed(_history(metric)):
                if bool(observed):
                    actual_duration += 1
                else:
                    break
    else:
        actual_duration = int(_decimal(metric))
    return actual_duration >= duration, actual_duration, duration


def _compare(actual: Any, operator: str, expected: Any, unit: str | None) -> tuple[bool, Any, Any]:
    if operator in {">", ">=", "<", "<="}:
        observed = _current(actual)
        threshold = _configured_number(expected, unit)
        return _ordered(observed, expected, operator, unit), observed, threshold
    if operator in {"=", "!="}:
        observed = _current(actual)
        result = _equal(observed, expected, unit)
        return (result if operator == "=" else not result), observed, expected
    if operator == "BETWEEN":
        if not isinstance(expected, (list, tuple)) or len(expected) != 2:
            raise ValueError("BETWEEN requires exactly two values")
        observed = _decimal(_current(actual))
        low = _configured_number(expected[0], unit)
        high = _configured_number(expected[1], unit)
        return low <= observed <= high, observed, (low, high)
    if operator in {"IN", "NOT_IN"}:
        if not isinstance(expected, (list, tuple, set, frozenset)):
            raise ValueError(f"{operator} requires a list of values")
        observed = _current(actual)
        result = any(_equal(observed, candidate, unit) for candidate in expected)
        return (not result if operator == "NOT_IN" else result), observed, list(expected)
    if operator in {"INCREASE_BY", "DECREASE_BY"}:
        change = _change(actual, decrease=operator == "DECREASE_BY", unit=unit)
        threshold = _configured_number(expected, unit)
        return change >= threshold, change, threshold
    if operator == "PERSISTENT_FOR":
        return _persistent(actual, expected, unit)
    raise ValueError(f"unsupported operator: {operator}")


def _metric(metrics: dict[str, Any], code: str, period: str | None) -> Any:
    exact_candidates = [f"{code}:{period}"] if period else []
    exact_candidates.append(code)
    for candidate in exact_candidates:
        if candidate in metrics:
            return metrics[candidate]
    normalized = {_token(key): value for key, value in metrics.items()}
    for candidate in exact_candidates:
        if _token(candidate) in normalized:
            return normalized[_token(candidate)]
    raise KeyError(code)


def validate_rule_definition(definition: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    conditions = definition.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        errors.append("conditions must contain at least one condition")
        return errors

    def visit(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path} must be an object")
            return
        children = node.get("conditions")
        if children is not None:
            logic = str(node.get("logic", node.get("operator", "AND"))).upper()
            if logic not in SUPPORTED_LOGIC:
                errors.append(f"{path}.logic is unsupported")
            if not isinstance(children, list) or not children:
                errors.append(f"{path}.conditions must not be empty")
                return
            if logic == "NOT" and len(children) != 1:
                errors.append(f"{path}.conditions must contain one item for NOT")
            for index, child in enumerate(children):
                visit(child, f"{path}.conditions[{index}]")
            return
        metric = node.get("metric")
        if not isinstance(metric, str) or not metric.strip():
            errors.append(f"{path}.metric is required")
        try:
            operator = canonical_operator(str(node.get("operator", "")))
        except ValueError:
            errors.append(f"{path}.operator is unsupported")
            return
        value = node.get("value")
        if operator == "BETWEEN" and (not isinstance(value, list) or len(value) != 2):
            errors.append(f"{path}.value must contain two values for BETWEEN")
        if operator in {"IN", "NOT_IN"} and not isinstance(value, list):
            errors.append(f"{path}.value must be a list for {operator}")
        if value is None:
            errors.append(f"{path}.value is required")

    root = {"logic": definition.get("logic", "AND"), "conditions": conditions}
    visit(root, "rule")
    recommendation = definition.get("recommendation")
    if not isinstance(recommendation, dict):
        errors.append("recommendation is required")
    else:
        if not isinstance(recommendation.get("opportunityType"), str):
            errors.append("recommendation.opportunityType must be a code")
        products = recommendation.get("products", [])
        if not isinstance(products, list) or any(not isinstance(item, str) for item in products):
            errors.append("recommendation.products must contain product codes only")
    return errors


@dataclass(frozen=True, slots=True)
class Evaluation:
    matched: bool
    confidence: float
    evidence: list[dict[str, Any]]
    explanation: dict[str, Any]


class RuleEvaluator:
    """Evaluate configured rules without embedding any business metric or threshold."""

    def evaluate(self, definition: dict[str, Any], metrics: dict[str, Any]) -> Evaluation:
        errors = validate_rule_definition(definition)
        if errors:
            raise ValueError("; ".join(errors))
        evidence: list[dict[str, Any]] = []

        def visit(node: dict[str, Any], path: str) -> tuple[bool, dict[str, Any]]:
            if "conditions" in node:
                logic = str(node.get("logic", node.get("operator", "AND"))).upper()
                evaluated = [
                    visit(child, f"{path}.{index}")
                    for index, child in enumerate(node["conditions"])
                ]
                child_results = [item[0] for item in evaluated]
                if logic == "AND":
                    result = all(child_results)
                elif logic == "OR":
                    result = any(child_results)
                else:
                    result = not child_results[0]
                return result, {
                    "type": "GROUP",
                    "logic": logic,
                    "result": result,
                    "children": [item[1] for item in evaluated],
                }
            metric_code = str(node["metric"])
            operator = canonical_operator(str(node["operator"]))
            period = str(node["period"]) if node.get("period") else None
            try:
                supplied = _metric(metrics, metric_code, period)
                result, observed, threshold = _compare(
                    supplied, operator, node.get("value"), node.get("unit")
                )
                unavailable_reason = None
            except (KeyError, TypeError, ValueError, InvalidOperation, ZeroDivisionError) as exc:
                result = False
                observed = None
                threshold = node.get("value")
                unavailable_reason = str(exc) or "metric unavailable"
            item = {
                "path": path,
                "metric": metric_code,
                "operator": operator,
                "actual": _json_value(observed),
                "threshold": _json_value(threshold),
                "unit": node.get("unit"),
                "period": period,
                "result": result,
            }
            if unavailable_reason:
                item["unavailableReason"] = unavailable_reason
            evidence.append(item)
            return result, {"type": "CONDITION", **item}

        root = {"logic": definition.get("logic", "AND"), "conditions": definition["conditions"]}
        matched, explanation = visit(root, "condition")
        confidence_config = definition.get("confidence") or {}
        base = _configured_number(confidence_config.get("baseScore", 0), "PERCENT")
        weights = confidence_config.get("weights") or {}
        passed_metrics = {item["metric"] for item in evidence if item["result"]}
        score = base + sum(
            (
                _configured_number(value, "PERCENT")
                for code, value in weights.items()
                if code in passed_metrics
            ),
            Decimal(0),
        )
        confidence = float(min(Decimal(1), max(Decimal(0), score)))
        if not math.isfinite(confidence):
            confidence = 0.0
        return Evaluation(matched, confidence, evidence, explanation)


__all__ = [
    "ENGINE_VERSION",
    "SUPPORTED_LOGIC",
    "SUPPORTED_OPERATORS",
    "Evaluation",
    "RuleEvaluator",
    "canonical_operator",
    "validate_rule_definition",
]
