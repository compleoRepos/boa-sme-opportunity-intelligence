from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DEFAULT_RULES_FILE = Path(__file__).with_name("rule-studio.json")
DEFAULT_PERSONA = {
    "subject": "seed-rule-studio",
    "username": "business.analyst.demo",
    "roles": ["ADMIN", "BUSINESS_ANALYST", "RULE_APPROVER"],
    "branchIds": ["ALL"],
    "relationshipManagerIds": [],
}


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    bearer_token: str | None = None,
    timeout: float = 30,
) -> tuple[int, dict[str, Any] | None]:
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Dev-Principal": json.dumps(DEFAULT_PERSONA, separators=(",", ":")),
    }
    if payload and payload.get("ruleId"):
        headers["Idempotency-Key"] = f"seed-rule-{payload['ruleId']}"
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except HTTPError as error:
        body = error.read()
        return error.code, json.loads(body) if body else None


def _oauth_token(token_url: str, client_id: str, client_secret: str) -> str:
    data = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    request = Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("OAuth token endpoint did not return an access_token")
    return token


def seed_rule_studio(
    rules_url: str,
    rules_file: Path = DEFAULT_RULES_FILE,
    *,
    bearer_token: str | None = None,
) -> list[dict[str, str]]:
    definitions = json.loads(rules_file.read_text(encoding="utf-8"))
    if not isinstance(definitions, list):
        raise ValueError("Rule Studio seed must be a JSON array.")

    results: list[dict[str, str]] = []
    endpoint = rules_url.rstrip("/")
    for definition in definitions:
        rule_id = str(definition["ruleId"])
        resource = f"{endpoint}/{quote(rule_id, safe='')}"
        status, _body = _request("GET", resource, bearer_token=bearer_token)
        if status == 200:
            results.append({"ruleId": rule_id, "status": "ALREADY_PRESENT"})
            continue
        if status != 404:
            raise RuntimeError(f"GET {resource} returned HTTP {status}")

        status, body = _request("POST", endpoint, payload=definition, bearer_token=bearer_token)
        if status == 201:
            results.append({"ruleId": rule_id, "status": "CREATED"})
            continue
        if status == 409:
            confirm_status, _confirm_body = _request("GET", resource, bearer_token=bearer_token)
            if confirm_status == 200:
                results.append({"ruleId": rule_id, "status": "ALREADY_PRESENT_AFTER_CONFLICT"})
                continue
        detail = json.dumps(body, ensure_ascii=False) if body is not None else "no response body"
        raise RuntimeError(f"POST {endpoint} for {rule_id} returned HTTP {status}: {detail}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed every governed Rule Studio demo rule independently and idempotently."
    )
    parser.add_argument("--rules-url", required=True)
    parser.add_argument("--rules-file", type=Path, default=DEFAULT_RULES_FILE)
    parser.add_argument("--token-url", default=os.getenv("RULE_SEED_TOKEN_URL"))
    parser.add_argument("--client-id", default=os.getenv("RULE_SEED_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.getenv("RULE_SEED_CLIENT_SECRET"))
    args = parser.parse_args()

    bearer_token = None
    if args.token_url:
        if not args.client_id or not args.client_secret:
            parser.error("client-id and client-secret are required when token-url is set")
        bearer_token = _oauth_token(args.token_url, args.client_id, args.client_secret)
    results = seed_rule_studio(args.rules_url, args.rules_file, bearer_token=bearer_token)
    for result in results:
        print(f"{result['status']} rule {result['ruleId']}")
    expected = {"SME_INVESTMENT_001", "SME_TRADE_001", "FLOW_DOMICILIATION_001"}
    actual = {result["ruleId"] for result in results}
    missing = sorted(expected - actual)
    if missing:
        print(f"Missing required demo rules: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
