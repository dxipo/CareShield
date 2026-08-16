import asyncio

import httpx
import pytest

from app.adapters.ezviz.client import EzvizClient
from app.adapters.ezviz.exceptions import EzvizApiError, EzvizResponseError
from app.adapters.ezviz.token_manager import EzvizTokenManager
from app.core.config import EzvizSettings


def test_token_response_parsing_and_cache_reuse() -> None:
    calls = 0
    now = [1_700_000_000.0]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "code": "200",
                "msg": "success",
                "data": {
                    "accessToken": f"test-token-{calls}",
                    "expireTime": int((now[0] + 600) * 1000),
                },
            },
        )

    async def scenario() -> None:
        settings = EzvizSettings("example-key", "example-secret")
        async with httpx.AsyncClient(
            base_url=settings.api_base_url,
            transport=httpx.MockTransport(handler),
        ) as client:
            manager = EzvizTokenManager(settings, client, clock=lambda: now[0])
            assert await manager.get_access_token() == "test-token-1"
            assert await manager.get_access_token() == "test-token-1"
            assert calls == 1

            now[0] += 301
            assert await manager.get_access_token() == "test-token-2"
            assert calls == 2

    asyncio.run(scenario())


def test_invalid_expire_time_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": "200",
                "data": {"accessToken": "test-token", "expireTime": "invalid"},
            },
        )

    async def scenario() -> None:
        settings = EzvizSettings("example-key", "example-secret")
        async with httpx.AsyncClient(
            base_url=settings.api_base_url,
            transport=httpx.MockTransport(handler),
        ) as client:
            manager = EzvizTokenManager(settings, client)
            with pytest.raises(EzvizResponseError):
                await manager.get_access_token()

    asyncio.run(scenario())


def test_api_error_is_safe_and_keeps_only_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": "10030", "msg": "credentials do not match"},
        )

    async def scenario() -> None:
        settings = EzvizSettings("example-key", "example-secret")
        client = EzvizClient(settings, transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(EzvizApiError) as error:
                await client.list_all_devices()
            assert error.value.code == "10030"
            assert "example-secret" not in str(error.value)
        finally:
            await client.close()

    asyncio.run(scenario())


def test_expired_token_response_triggers_one_refresh() -> None:
    token_calls = 0
    list_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, list_calls
        if request.url.path == "/api/lapp/token/get":
            token_calls += 1
            return httpx.Response(
                200,
                json={
                    "code": "200",
                    "data": {
                        "accessToken": f"test-token-{token_calls}",
                        "expireTime": 4_000_000_000_000,
                    },
                },
            )

        list_calls += 1
        if list_calls == 1:
            return httpx.Response(200, json={"code": "10002", "msg": "expired"})
        return httpx.Response(
            200,
            json={"code": "200", "data": [], "page": {"total": 0}},
        )

    async def scenario() -> None:
        settings = EzvizSettings("example-key", "example-secret")
        client = EzvizClient(settings, transport=httpx.MockTransport(handler))
        try:
            assert await client.list_all_devices() == []
            assert token_calls == 2
            assert list_calls == 2
        finally:
            await client.close()

    asyncio.run(scenario())
