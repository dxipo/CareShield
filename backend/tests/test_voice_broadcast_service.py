import asyncio

import pytest

from app.adapters.ezviz.exceptions import (
    EzvizVoiceUnsupportedError,
    EzvizVoiceValidationError,
)
from app.schemas.device import DeviceDetail
from app.services.voice_broadcast_service import VoiceBroadcastService


class FakeDeviceService:
    def __init__(self, support_talk: str = "1") -> None:
        self.support_talk = support_talk
        self.sent: dict[str, object] | None = None

    async def get_device(self, device_serial: str) -> DeviceDetail:
        return DeviceDetail(
            id="ezviz_safe_id",
            device_serial=device_serial,
            online=True,
            status="online",
        )

    async def get_device_capacity(self, device_serial: str, *, channel_no: int):
        return {"support_talk": self.support_talk, "support_alarm_voice": "1"}

    async def send_voice_once(self, device_serial: str, **kwargs) -> None:
        self.sent = {"device_serial": device_serial, **kwargs}


def test_voice_broadcast_validates_capability_and_sends_transient_audio() -> None:
    async def scenario() -> None:
        devices = FakeDeviceService()
        service = VoiceBroadcastService(devices)  # type: ignore[arg-type]

        capability = await service.capability("TEST-SERIAL")
        assert capability.supported is True
        assert capability.support_talk == 1

        result = await service.send_once(
            "TEST-SERIAL",
            channel_no=1,
            filename="alert.wav",
            content=b"test-audio",
        )
        assert result.status == "accepted"
        assert devices.sent is not None
        assert devices.sent["content_type"] == "audio/wav"

    asyncio.run(scenario())


def test_voice_broadcast_rejects_unsupported_device_and_invalid_audio() -> None:
    async def scenario() -> None:
        unsupported = VoiceBroadcastService(  # type: ignore[arg-type]
            FakeDeviceService(support_talk="0")
        )
        with pytest.raises(EzvizVoiceUnsupportedError):
            await unsupported.send_once(
                "TEST-SERIAL",
                channel_no=1,
                filename="alert.wav",
                content=b"test-audio",
            )

        service = VoiceBroadcastService(FakeDeviceService())  # type: ignore[arg-type]
        with pytest.raises(EzvizVoiceValidationError):
            await service.send_once(
                "TEST-SERIAL",
                channel_no=1,
                filename="alert.txt",
                content=b"not-audio",
            )

    asyncio.run(scenario())
