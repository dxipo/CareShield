from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx

from app.alerts.voice_alert import FraudVoiceAlert
from app.core.config import load_settings


def test_voice_alert_sends_once_per_alert_lifecycle_and_honors_cooldown(
    tmp_path,
) -> None:
    async def run() -> None:
        audio = tmp_path / "fraud-warning.aac"
        audio.write_bytes(b"safe-test-audio")
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert request.headers["Authorization"] == "Bearer internal-test-token"
            assert request.url.path == "/internal/media/devices/TEST-SERIAL/voice"
            assert request.url.params["filename"] == "fraud-warning.aac"
            assert request.url.params["channel_no"] == "1"
            assert request.content == b"safe-test-audio"
            return httpx.Response(200, json={"status": "accepted"})

        settings = replace(
            load_settings(),
            backend_internal_url="http://backend.test",
            shared_token="internal-test-token",
            voice_alert_enabled=True,
            voice_alert_audio_path=str(audio),
            voice_alert_cooldown_seconds=300,
        )
        alert = FraudVoiceAlert(settings, transport=httpx.MockTransport(handler))

        assert await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=True
        )
        assert not await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=True
        )
        assert not await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=False
        )
        assert not await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=True
        )
        assert alert.status == "cooldown"
        assert len(requests) == 1
        metadata = alert.metadata()
        assert "audio_path" not in metadata
        assert "internal-test-token" not in str(metadata)
        await alert.close()

    asyncio.run(run())


def test_voice_alert_reports_quota_without_leaking_response_or_retrying(
    tmp_path,
) -> None:
    async def run() -> None:
        audio = tmp_path / "warning.wav"
        audio.write_bytes(b"safe-test-audio")
        calls = 0

        async def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                503,
                json={"detail": "EZVIZ voice broadcast quota is unavailable"},
            )

        settings = replace(
            load_settings(),
            backend_internal_url="http://backend.test",
            shared_token="internal-test-token",
            voice_alert_enabled=True,
            voice_alert_audio_path=str(audio),
        )
        alert = FraudVoiceAlert(settings, transport=httpx.MockTransport(handler))

        assert not await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=True
        )
        assert alert.status == "quota_unavailable"
        assert not await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=True
        )
        assert calls == 1
        assert "resource body" not in str(alert.metadata())
        await alert.close()

    asyncio.run(run())


def test_voice_alert_is_safe_and_inert_by_default() -> None:
    async def run() -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            raise AssertionError("disabled alert must not call Backend")

        settings = replace(
            load_settings(),
            backend_internal_url="http://backend.test",
            shared_token="internal-test-token",
        )
        alert = FraudVoiceAlert(settings, transport=httpx.MockTransport(handler))
        assert not alert.enabled
        assert not await alert.handle_decision(
            device_id="TEST-SERIAL", alert_active=True
        )
        assert alert.status == "disabled"
        await alert.close()

    asyncio.run(run())
