from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

FORBIDDEN_TERMS = (
    "credit score",
    "credit_score",
    "risk score",
    "risk_score",
    "default probability",
    "default_probability",
    "credit decision",
    "credit_decision",
    "probabilité de défaut",
    "décision de crédit",
    "score de risque",
)


def canonical_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def ensure_relational_language(payload: Mapping[str, Any]) -> None:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).casefold()
    matches = [term for term in FORBIDDEN_TERMS if term in serialized]
    if matches:
        raise ValueError(f"forbidden credit-decision vocabulary: {matches[0]}")


class DecisionAuditBuilder:
    def build(
        self,
        *,
        decision_id: str,
        opportunity: Mapping[str, Any],
        inputs: Mapping[str, Any],
        config_id: str,
        config_checksum: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        ensure_relational_language(opportunity)
        body = {
            "decision_id": decision_id,
            "opportunity": dict(opportunity),
            "inputs": dict(inputs),
            "config_id": config_id,
            "config_checksum": config_checksum,
            "correlation_id": correlation_id,
        }
        return {
            **body,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "decision_hash": canonical_hash(body),
        }
