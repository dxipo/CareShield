import hashlib
from datetime import UTC, datetime
from typing import Any

from app.adapters.ezviz.client import EzvizClient
from app.adapters.ezviz.exceptions import (
    EzvizDeviceNotFoundError,
    EzvizError,
    EzvizNotConfiguredError,
    EzvizResponseError,
)
from app.core.config import EzvizSettings
from app.schemas.device import (
    DeviceChannel,
    DeviceDetail,
    DeviceSummary,
    EzvizIntegrationStatus,
)


class DeviceService:
    def __init__(
        self,
        settings: EzvizSettings,
        client: EzvizClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client if client is not None else (
            EzvizClient(settings) if settings.configured else None
        )

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

    async def integration_status(self) -> EzvizIntegrationStatus:
        if not self.settings.configured:
            return EzvizIntegrationStatus(
                configured=False,
                reachable=False,
                message="EZVIZ integration is not configured",
            )

        try:
            await self._require_client().check_reachable()
        except EzvizError as exc:
            return EzvizIntegrationStatus(
                configured=True,
                reachable=False,
                message=str(exc),
            )

        return EzvizIntegrationStatus(configured=True, reachable=True)

    async def list_devices(self) -> list[DeviceSummary]:
        raw_devices = await self._require_client().list_all_devices()
        return [self._map_summary(device) for device in raw_devices]

    async def get_device(self, device_serial: str) -> DeviceDetail:
        raw_device = await self._require_client().get_device_info(device_serial)
        if raw_device is None:
            raise EzvizDeviceNotFoundError("EZVIZ device was not found")
        return self._map_detail(raw_device, fallback_serial=device_serial)

    async def get_device_capacity(
        self,
        device_serial: str,
        *,
        channel_no: int = 1,
    ) -> dict[str, Any]:
        return await self._require_client().get_device_capacity(
            device_serial,
            channel_no=channel_no,
        )

    async def send_voice_once(
        self,
        device_serial: str,
        *,
        channel_no: int,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> None:
        await self._require_client().send_voice_once(
            device_serial,
            channel_no=channel_no,
            filename=filename,
            content=content,
            content_type=content_type,
        )

    def _require_client(self) -> EzvizClient:
        if not self.settings.configured or self.client is None:
            raise EzvizNotConfiguredError("EZVIZ integration is not configured")
        return self.client

    @classmethod
    def _map_summary(cls, raw: dict[str, Any]) -> DeviceSummary:
        serial = cls._optional_string(raw.get("deviceSerial"))
        if serial is None:
            raise EzvizResponseError("EZVIZ device response has no device serial")

        online, status = cls._map_status(raw.get("status"))
        channels = cls._map_channels(raw.get("cameraInfo"))
        camera_count = cls._optional_int(raw.get("cameraNum"))
        if camera_count is None and channels:
            camera_count = len(channels)

        return DeviceSummary(
            id=cls._stable_device_id(serial),
            device_serial=serial,
            name=cls._optional_string(raw.get("deviceName")),
            model=cls._optional_string(raw.get("deviceType") or raw.get("model")),
            online=online,
            status=status,
            device_type=cls._optional_string(
                raw.get("parentCategory") or raw.get("category")
            ),
            camera_count=camera_count,
            channels=channels,
            updated_at=cls._timestamp(raw.get("updateTime")),
        )

    @classmethod
    def _map_detail(
        cls,
        raw: dict[str, Any],
        *,
        fallback_serial: str,
    ) -> DeviceDetail:
        summary = cls._map_summary({"deviceSerial": fallback_serial, **raw})
        return DeviceDetail(
            **summary.model_dump(),
            local_name=cls._optional_string(raw.get("localName")),
            firmware_version=cls._optional_string(raw.get("deviceVersion")),
            network_type=cls._optional_string(raw.get("netType")),
            signal=cls._optional_string(raw.get("signal")),
        )

    @staticmethod
    def _stable_device_id(serial: str) -> str:
        digest = hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16]
        return f"ezviz_{digest}"

    @staticmethod
    def _map_status(value: Any) -> tuple[bool | None, str]:
        if value == 1 or value == "1":
            return True, "online"
        if value == 0 or value == "0":
            return False, "offline"
        return None, "unknown"

    @staticmethod
    def _map_channels(value: Any) -> list[DeviceChannel]:
        if not isinstance(value, list):
            return []
        channels: list[DeviceChannel] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            channels.append(
                DeviceChannel(
                    number=DeviceService._optional_int(item.get("cameraNo")),
                    name=DeviceService._optional_string(item.get("cameraName")),
                )
            )
        return channels

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        try:
            milliseconds = int(value)
        except (TypeError, ValueError):
            return None
        try:
            return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None
