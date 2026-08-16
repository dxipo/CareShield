import asyncio

import httpx

from app.adapters.ezviz.exceptions import EzvizDeviceOfflineError
from app.api.dependencies import get_stream_service
from app.main import app
from app.schemas.stream import StreamPlayback


async def request(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


class FakeStreamService:
    def __init__(self, *, offline: bool = False) -> None:
        self.offline = offline

    async def get_live_stream(self, *_args: object, **_kwargs: object) -> StreamPlayback:
        if self.offline:
            raise EzvizDeviceOfflineError("offline")
        return StreamPlayback(
            device_id="ezviz_safeid",
            channel_no=1,
            playback_url="https://example.invalid/live.m3u8?temporary=1",
            expires_at=None,
            quality="high",
        )


def test_stream_endpoint_never_exposes_credentials() -> None:
    secret = "must-never-appear"
    token = "access-token-must-never-appear"
    service = FakeStreamService()

    async def override_service() -> FakeStreamService:
        return service

    app.dependency_overrides[get_stream_service] = override_service
    try:
        response = asyncio.run(request("/api/devices/TEST123456/stream"))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["protocol"] == "hls"
    assert secret not in response.text
    assert token not in response.text
    assert "accessToken" not in response.text
    assert "appSecret" not in response.text


def test_stream_endpoint_maps_offline_device() -> None:
    service = FakeStreamService(offline=True)

    async def override_service() -> FakeStreamService:
        return service

    app.dependency_overrides[get_stream_service] = override_service
    try:
        response = asyncio.run(request("/api/devices/OFFLINE/stream"))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "EZVIZ device is offline"}
