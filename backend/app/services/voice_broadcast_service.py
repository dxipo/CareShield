from pathlib import PurePath

from app.adapters.ezviz.exceptions import (
    EzvizDeviceOfflineError,
    EzvizVoiceUnsupportedError,
    EzvizVoiceValidationError,
)
from app.schemas.voice import VoiceBroadcastCapability, VoiceBroadcastResult
from app.services.device_service import DeviceService


class VoiceBroadcastService:
    # The API page accepts up to 20 MB, while the current product operation
    # guide specifies 5 MB. Use the stricter product limit for interoperability.
    MAX_AUDIO_BYTES = 5 * 1024 * 1024
    CONTENT_TYPES = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".aac": "audio/aac",
    }

    def __init__(self, device_service: DeviceService) -> None:
        self.device_service = device_service

    async def capability(
        self,
        device_serial: str,
        *,
        channel_no: int = 1,
    ) -> VoiceBroadcastCapability:
        device = await self.device_service.get_device(device_serial)
        if device.online is False:
            raise EzvizDeviceOfflineError("EZVIZ device is offline")

        data = await self.device_service.get_device_capacity(
            device_serial,
            channel_no=channel_no,
        )
        support_talk = self._optional_int(data.get("support_talk"))
        alarm_voice = self._optional_bool(data.get("support_alarm_voice"))
        return VoiceBroadcastCapability(
            supported=support_talk in {1, 3},
            support_talk=support_talk,
            support_alarm_voice=alarm_voice,
        )

    async def send_once(
        self,
        device_serial: str,
        *,
        channel_no: int,
        filename: str,
        content: bytes,
    ) -> VoiceBroadcastResult:
        suffix = PurePath(filename).suffix.lower()
        if suffix not in self.CONTENT_TYPES:
            raise EzvizVoiceValidationError("Audio format is not supported")
        if not content or len(content) > self.MAX_AUDIO_BYTES:
            raise EzvizVoiceValidationError("Audio file size is invalid")

        capability = await self.capability(device_serial, channel_no=channel_no)
        if not capability.supported:
            raise EzvizVoiceUnsupportedError(
                "EZVIZ device does not support transient voice broadcast"
            )

        await self.device_service.send_voice_once(
            device_serial,
            channel_no=channel_no,
            filename=PurePath(filename).name,
            content=content,
            content_type=self.CONTENT_TYPES[suffix],
        )
        return VoiceBroadcastResult(channel_no=channel_no)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_bool(value: object) -> bool | None:
        if value in {1, "1", True}:
            return True
        if value in {0, "0", False}:
            return False
        return None
