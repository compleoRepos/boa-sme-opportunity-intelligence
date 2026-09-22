from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from database.seed import rule_studio


def _rules_file(tmp_path: Path) -> Path:
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            [
                {"ruleId": "ALREADY", "name": "Déjà présente"},
                {"ruleId": "CREATE", "name": "À créer"},
                {"ruleId": "RACE", "name": "Conflit concurrent"},
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_seed_rule_studio_is_idempotent_per_rule(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    race_gets = 0

    def fake_request(
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        bearer_token: str | None = None,
        timeout: float = 30,
    ) -> tuple[int, dict[str, Any] | None]:
        nonlocal race_gets
        del timeout
        assert bearer_token == "seed-token"
        calls.append((method, url))
        if method == "GET" and url.endswith("/ALREADY"):
            return 200, {"ruleId": "ALREADY"}
        if method == "GET" and url.endswith("/CREATE"):
            return 404, None
        if method == "POST" and payload and payload["ruleId"] == "CREATE":
            return 201, {"ruleId": "CREATE"}
        if method == "GET" and url.endswith("/RACE"):
            race_gets += 1
            return (404, None) if race_gets == 1 else (200, {"ruleId": "RACE"})
        if method == "POST" and payload and payload["ruleId"] == "RACE":
            return 409, {"code": "RULE_ALREADY_EXISTS"}
        raise AssertionError((method, url, payload))

    monkeypatch.setattr(rule_studio, "_request", fake_request)
    results = rule_studio.seed_rule_studio(
        "http://rule-management:8080/internal/v1/rules",
        _rules_file(tmp_path),
        bearer_token="seed-token",
    )

    assert results == [
        {"ruleId": "ALREADY", "status": "ALREADY_PRESENT"},
        {"ruleId": "CREATE", "status": "CREATED"},
        {"ruleId": "RACE", "status": "ALREADY_PRESENT_AFTER_CONFLICT"},
    ]
    assert calls.count(("GET", "http://rule-management:8080/internal/v1/rules/ALREADY")) == 1
    assert calls.count(("GET", "http://rule-management:8080/internal/v1/rules/CREATE")) == 1
    assert calls.count(("GET", "http://rule-management:8080/internal/v1/rules/RACE")) == 2
