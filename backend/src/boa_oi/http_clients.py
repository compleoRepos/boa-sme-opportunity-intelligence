from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from boa_oi.adapters.ports import (
    CanonicalAccount,
    CanonicalCustomer,
    CanonicalTransaction,
)
from boa_oi.platform import Problem, auth_disabled, oidc_internal_issuer


class ServiceTokenProvider:
    def __init__(self) -> None:
        self._token: str | None = None

    async def token(self) -> str | None:
        if auth_disabled():
            return None
        if self._token:
            return self._token
        client_id = os.getenv("OAUTH_CLIENT_ID")
        client_secret = os.getenv("OAUTH_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise Problem(
                503,
                "AUTH_CONFIGURATION_ERROR",
                "Service OAuth credentials are not configured.",
            )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{oidc_internal_issuer()}/protocol/openid-connect/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            raise Problem(
                503,
                "AUTH_PROVIDER_UNAVAILABLE",
                "A service token could not be obtained.",
            ) from exc
        self._token = str(response.json()["access_token"])
        return self._token


_token_provider = ServiceTokenProvider()


async def service_request(
    method: str,
    url: str,
    *,
    correlation_id: str,
    json: Any | None = None,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    timeout: float = 15.0,
    incoming_authorization: str | None = None,
    dev_principal: str | None = None,
) -> Any:
    headers = {"X-Correlation-ID": correlation_id, "Accept": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if dev_principal and auth_disabled():
        headers["X-Dev-Principal"] = dev_principal
    token = None if incoming_authorization else await _token_provider.token()
    if incoming_authorization:
        headers["Authorization"] = incoming_authorization
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, headers=headers, json=json, params=params)
    except httpx.TimeoutException as exc:
        raise Problem(504, "DEPENDENCY_TIMEOUT", "A dependent service timed out.") from exc
    except httpx.HTTPError as exc:
        raise Problem(503, "DEPENDENCY_UNAVAILABLE", "A dependent service is unavailable.") from exc
    if response.status_code >= 400:
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = body.get("code") or "DEPENDENCY_ERROR"
        message = body.get("message") or "A dependent service rejected the request."
        if response.status_code in {401, 403, 404, 409, 422}:
            raise Problem(response.status_code, code, message, details=body.get("details"))
        if response.status_code == 504:
            raise Problem(504, "DEPENDENCY_TIMEOUT", message)
        raise Problem(502, "DEPENDENCY_UNAVAILABLE", message)
    if response.status_code == 204:
        return None
    return response.json()


class HttpBankingAdapter:
    """HTTP implementation of banking ports; the remote implementation is configuration only."""

    def __init__(self, base_url: str | None = None) -> None:
        configured = (
            base_url
            or os.getenv("BANKING_API_URL")
            or os.getenv("MOCK_BANKING_API_URL")
            or os.getenv("MOCK_BANK_URL")
        )
        if not configured:
            raise Problem(
                503,
                "BANKING_ADAPTER_CONFIGURATION_ERROR",
                "BANKING_API_URL is not configured.",
            )
        self.base_url = configured.rstrip("/")

    async def fetch_customers(self, count: int, correlation_id: str) -> list[dict[str, Any]]:
        return await service_request(
            "GET",
            f"{self.base_url}/mock/v1/customers",
            correlation_id=correlation_id,
            params={"customerCount": count},
        )

    async def fetch_accounts(self, count: int, correlation_id: str) -> list[dict[str, Any]]:
        return await service_request(
            "GET",
            f"{self.base_url}/mock/v1/accounts",
            correlation_id=correlation_id,
            params={"customerCount": count},
        )

    async def fetch_balances(self, count: int, correlation_id: str) -> list[dict[str, Any]]:
        return await service_request(
            "GET",
            f"{self.base_url}/mock/v1/balances",
            correlation_id=correlation_id,
            params={"customerCount": count},
            timeout=30,
        )

    async def fetch_transactions(
        self,
        from_date: date,
        to_date: date,
        count: int,
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        return await service_request(
            "GET",
            f"{self.base_url}/mock/v1/transactions",
            correlation_id=correlation_id,
            params={
                "fromDate": from_date.isoformat(),
                "toDate": to_date.isoformat(),
                "customerCount": count,
            },
            timeout=60,
        )

    async def fetch_products(self, count: int, correlation_id: str) -> dict[str, Any]:
        return await service_request(
            "GET",
            f"{self.base_url}/mock/v1/products",
            correlation_id=correlation_id,
            params={"customerCount": count},
        )

    @staticmethod
    def canonical_customer(row: dict[str, Any]) -> CanonicalCustomer:
        return CanonicalCustomer(
            customer_ref=row["customerId"],
            legal_name=row["legalName"],
            sector_code=row["sector"],
            segment_code=row["segment"],
        )

    @staticmethod
    def canonical_account(row: dict[str, Any]) -> CanonicalAccount:
        return CanonicalAccount(
            account_ref=row["accountId"],
            customer_ref=row["customerId"],
            account_type=row["accountType"],
            currency=row["currency"],
        )

    @staticmethod
    def canonical_transaction(row: dict[str, Any]) -> CanonicalTransaction:
        return CanonicalTransaction(
            transaction_ref=row["transactionId"],
            account_ref=row["accountId"],
            value_date=date.fromisoformat(row["valueDate"]),
            direction=row["direction"],
            amount=Decimal(str(row["amount"])),
            currency=row["currency"],
            category=row["category"],
            international=bool(row["international"]),
        )


__all__ = ["HttpBankingAdapter", "ServiceTokenProvider", "service_request"]
