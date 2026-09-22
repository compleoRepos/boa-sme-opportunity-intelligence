from __future__ import annotations

from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from boa_oi.platform import create_service_app, get_session, require_roles
from boa_oi.rules import ENGINE_VERSION, RuleEvaluator
from boa_oi.rules.schemas import EvaluationRequest
from boa_oi.rules.service import active_versions

app = create_service_app(
    "rule-engine-service",
    "Generic, deterministic evaluation of ACTIVE rule versions with evidence and explanations.",
)
PREFIX = "/internal/v1/rules"
ENGINE_ROLES = ("SERVICE", "ADMIN", "DATA_ANALYST", "BUSINESS_ANALYST", "RULE_APPROVER")


@app.post(
    f"{PREFIX}/evaluate",
    dependencies=[Depends(require_roles(*ENGINE_ROLES))],
    tags=["Rule Engine"],
)
def evaluate(
    payload: EvaluationRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    evaluator = RuleEvaluator()
    results: list[dict[str, Any]] = []
    active = active_versions(session)
    evaluated_versions = [f"{rule.rule_id}:v{version.version}" for rule, version in active]
    for rule, version in active:
        evaluation = evaluator.evaluate(version.configuration_json, payload.metrics)
        if not evaluation.matched:
            continue
        recommendation = version.configuration_json["recommendation"]
        results.append(
            {
                "matched": True,
                "customerId": payload.customerId,
                "ruleId": rule.rule_id,
                "ruleName": rule.name,
                "ruleVersion": version.version,
                "engineVersion": ENGINE_VERSION,
                "opportunityType": recommendation["opportunityType"],
                "productCodes": recommendation.get("products", []),
                "horizon": recommendation.get("horizon"),
                "what": recommendation.get("what"),
                "whenText": recommendation.get("whenText"),
                "lifecycle": version.configuration_json.get("lifecycle", {}),
                "confidence": evaluation.confidence,
                "evidence": evaluation.evidence,
                "explanation": evaluation.explanation,
            }
        )
    if len(results) == 1:
        return {**results[0], "evaluatedRuleVersions": evaluated_versions}
    return {
        "matched": bool(results),
        "customerId": payload.customerId,
        "engineVersion": ENGINE_VERSION,
        "evaluatedRuleVersions": evaluated_versions,
        "matches": results,
    }


__all__ = ["app"]
