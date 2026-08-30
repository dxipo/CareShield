import asyncio

import httpx

from app.api.dependencies import get_device_service, get_stream_service
from app.main import app
from app.schemas.device import DeviceSummary
from app.schemas.stream import StreamPlayback


class FakeDeviceService:
    async def list_devices(self):
        return [
            DeviceSummary(
                id="ezviz_safe_id",
                device_serial="TEST-SERIAL",
                name="Test Camera",
                model="H6c",
                online=True,
                status="online",
            )
        ]


class FakeStreamService:
    expected_protocol = "http_flv"

    async def get_live_stream(self, device_serial, *, channel_no, quality, protocol):
        assert device_serial == "TEST-SERIAL"
        assert protocol == self.expected_protocol
        return StreamPlayback(
            device_id="ezviz_safe_id",
            channel_no=channel_no,
            protocol=protocol,
            playback_url=f"https://temporary.invalid/live.{protocol}",
            expires_at=None,
            quality=quality,
            container="flv" if protocol == "http_flv" else "mpeg-ts",
        )


def get(path: str, token: str | None) -> httpx.Response:
    async def request() -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path, headers=headers)

    return asyncio.run(request())


def test_internal_media_requires_worker_auth_and_returns_no_ezviz_secrets(monkeypatch) -> None:
    async def devices():
        return FakeDeviceService()

    async def streams():
        return FakeStreamService()

    app.dependency_overrides[get_device_service] = devices
    app.dependency_overrides[get_stream_service] = streams
    monkeypatch.setenv("AI_WORKER_SHARED_TOKEN", "internal-test-token")
    try:
        denied = get("/internal/media/devices", "wrong-token")
        devices_response = get("/internal/media/devices", "internal-test-token")
        stream_response = get(
            "/internal/media/devices/TEST-SERIAL/stream",
            "internal-test-token",
        )
    finally:
        app.dependency_overrides.clear()

    assert denied.status_code == 401
    assert devices_response.status_code == 200
    assert stream_response.status_code == 200
    assert stream_response.json()["protocol"] == "http_flv"
    assert stream_response.json()["container"] == "flv"
    combined = devices_response.text + stream_response.text
    assert "internal-test-token" not in combined
    assert "appSecret" not in combined
    assert "accessToken" not in combined


def test_internal_media_allows_batch_worker_to_request_hls(monkeypatch) -> None:
    async def streams():
        service = FakeStreamService()
        service.expected_protocol = "hls"
        return service

    app.dependency_overrides[get_stream_service] = streams
    monkeypatch.setenv("AI_WORKER_SHARED_TOKEN", "internal-test-token")
    try:
        response = get(
            "/internal/media/devices/TEST-SERIAL/stream?protocol=hls",
            "internal-test-token",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["protocol"] == "hls"
    assert response.json()["container"] == "mpeg-ts"
