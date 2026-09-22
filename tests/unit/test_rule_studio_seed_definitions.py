from __future__ import annotations

import json
from pathlib import Path

from boa_oi.rules.domain import validate_rule_definition
from boa_oi.rules.schemas import RuleDefinition


def test_rule_studio_seed_contains_three_valid_drafts() -> None:
    path = Path(__file__).parents[2] / "database" / "seed" / "rule-studio.json"
    definitions = json.loads(path.read_text(encoding="utf-8"))

    assert [item["ruleId"] for item in definitions] == [
        "SME_INVESTMENT_001",
        "SME_TRADE_001",
        "FLOW_DOMICILIATION_001",
    ]
    for definition in definitions:
        validated = RuleDefinition.model_validate(definition).model_dump(exclude_none=True)
        assert validate_rule_definition(validated) == []
