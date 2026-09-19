from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import httpx
import pytest
from boa_oi import http_clients
from boa_oi.platform import Problem


class FakeAsyncClient:
    token_calls = 0
    request_tokens: ClassVar[list[str | None]] = []
    malformed_token_response = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        del args

    async def post(self, url: str, data: dict[str, str]) -> httpx.Response:
        del data
        type(self).token_calls += 1
        payload = (
            {"expires_in": "not-a-number"}
            if type(self).malformed_token_response
            else {
                "access_token": f"service-token-{type(self).token_calls}",
                "expires_in": 100,
            }
        )
        return httpx.Response(
            200,
            json=payload,
            request=httpx.Request("POST", url),
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: Any,
        params: dict[str, Any] | None,
    ) -> httpx.Response:
        del json, params
        authorization = headers.get("Authorization")
        type(self).request_tokens.append(authorization)
        status = 401 if authorization == "Bearer service-token-1" else 200
        payload = (
            {"code": "TOKEN_EXPIRED", "message": "expired"} if status == 401 else {"status": "ok"}
        )
        return httpx.Response(
            status,
            json=payload,
            request=httpx.Request(method, url),
        )


def configure_oauth(monkeypatch) -> None:
    monkeypatch.setenv("BOA_AUTH_DISABLED", "false")
    monkeypatch.setenv("OAUTH_CLIENT_ID", "test-service")
    monkeypatch.setenv("OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("OIDC_ISSUER_URL", "http://identity/realms/test")
    monkeypatch.setattr(http_clients.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.token_calls = 0
    FakeAsyncClient.request_tokens = []
    FakeAsyncClient.malformed_token_response = False


def test_service_token_is_refreshed_before_expiration(monkeypatch) -> None:
    configure_oauth(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(http_clients.time, "monotonic", lambda: clock[0])
    provider = http_clients.ServiceTokenProvider()

    first = asyncio.run(provider.token())
    clock[0] = 169.0
    cached = asyncio.run(provider.token())
    clock[0] = 170.0
    refreshed = asyncio.run(provider.token())

    assert first == cached == "service-token-1"
    assert refreshed == "service-token-2"
    assert FakeAsyncClient.token_calls == 2


def test_service_request_refreshes_once_after_401(monkeypatch) -> None:
    configure_oauth(monkeypatch)
    monkeypatch.setattr(http_clients.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(http_clients, "_token_provider", http_clients.ServiceTokenProvider())

    result = asyncio.run(
        http_clients.service_request(
            "POST",
            "http://opportunity/internal/v1/opportunities/example/transition",
            correlation_id="corr-oauth-refresh",
            json={"status": "CONTACTED", "reason": "test"},
        )
    )

    assert result == {"status": "ok"}
    assert FakeAsyncClient.token_calls == 2
    assert FakeAsyncClient.request_tokens == [
        "Bearer service-token-1",
        "Bearer service-token-2",
    ]


def test_concurrent_service_token_requests_share_one_refresh(monkeypatch) -> None:
    configure_oauth(monkeypatch)
    monkeypatch.setattr(http_clients.time, "monotonic", lambda: 100.0)
    provider = http_clients.ServiceTokenProvider()

    async def gather_tokens() -> list[str | None]:
        return list(await asyncio.gather(*(provider.token() for _ in range(5))))

    tokens = asyncio.run(gather_tokens())

    assert tokens == ["service-token-1"] * 5
    assert FakeAsyncClient.token_calls == 1


def test_malformed_service_token_response_is_controlled(monkeypatch) -> None:
    configure_oauth(monkeypatch)
    FakeAsyncClient.malformed_token_response = True
    provider = http_clients.ServiceTokenProvider()

    with pytest.raises(Problem) as captured:
        asyncio.run(provider.token())

    assert captured.value.status_code == 503
    assert captured.value.code == "AUTH_PROVIDER_UNAVAILABLE"
