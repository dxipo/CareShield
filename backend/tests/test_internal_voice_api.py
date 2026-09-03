import asyncio

import httpx

from app.api.dependencies import get_voice_broadcast_service
from app.main import app
from app.schemas.voice import VoiceBroadcastCapability, VoiceBroadcastResult


class FakeVoiceBroadcastService:
    received: bytes | None = None

    async def capability(self, device_serial: str, *, channel_no: int):
        assert device_serial == "TEST-SERIAL"
        return VoiceBroadcastCapability(
            supported=True,
            support_talk=1,
            support_alarm_voice=True,
        )

    async def send_once(
        self,
        device_serial: str,
        *,
        channel_no: int,
        filename: str,
        content: bytes,
    ):
        assert device_serial == "TEST-SERIAL"
        assert filename == "alert.wav"
        self.received = content
        return VoiceBroadcastResult(channel_no=channel_no)


def test_internal_voice_api_requires_auth_and_never_returns_audio_or_secrets(
    monkeypatch,
) -> None:
    service = FakeVoiceBroadcastService()

    async def dependency():
        return service

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get(
                "/internal/media/devices/TEST-SERIAL/voice/capability"
            )
            headers = {"Authorization": "Bearer internal-test-token"}
            capability = await client.get(
                "/internal/media/devices/TEST-SERIAL/voice/capability",
                headers=headers,
            )
            sent = await client.post(
                "/internal/media/devices/TEST-SERIAL/voice?filename=alert.wav",
                headers={**headers, "Content-Type": "application/octet-stream"},
                content=b"test-audio",
            )
            return denied, capability, sent

    app.dependency_overrides[get_voice_broadcast_service] = dependency
    monkeypatch.setenv("AI_WORKER_SHARED_TOKEN", "internal-test-token")
    try:
        denied, capability, sent = asyncio.run(scenario())
    finally:
        app.dependency_overrides.clear()

    assert denied.status_code == 401
    assert capability.status_code == 200
    assert capability.json()["supported"] is True
    assert sent.status_code == 200
    assert sent.json() == {"provider": "ezviz", "status": "accepted", "channel_no": 1}
    assert service.received == b"test-audio"
    combined = capability.text + sent.text
    assert "test-audio" not in combined
    assert "internal-test-token" not in combined
    assert "accessToken" not in combined
