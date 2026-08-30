import asyncio
from uuid import uuid4

import httpx
import pytest

from app.adapters.motionclip import MotionClipClient, MotionClipError


def test_motionclip_error_does_not_expose_internal_response_or_token() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="token=upstream-secret /data/private/input.npz")

    async def run() -> None:
        client = MotionClipClient("http://motionclip.invalid", "worker-secret")
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(MotionClipError) as captured:
            await client.predict(uuid4())
        message = str(captured.value)
        assert "upstream-secret" not in message
        assert "worker-secret" not in message
        assert "/data/" not in message
        await client.close()

    asyncio.run(run())


def test_motionclip_health_requires_explicit_ready_true() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "unavailable", "ready": False})

    async def run() -> None:
        client = MotionClipClient("http://motionclip.invalid", "worker-secret")
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert await client.refresh_health() is False
        assert client.ready is False
        await client.close()

    asyncio.run(run())
