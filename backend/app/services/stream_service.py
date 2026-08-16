from typing import Literal

from app.adapters.ezviz.exceptions import EzvizNotConfiguredError
from app.adapters.ezviz.stream import EzvizStreamAdapter
from app.schemas.stream import StreamPlayback
from app.services.device_service import DeviceService


class StreamService:
    def __init__(
        self,
        device_service: DeviceService,
        adapter: EzvizStreamAdapter | None = None,
    ) -> None:
        self.device_service = device_service
        self.adapter = adapter

    async def get_live_stream(
        self,
        device_serial: str,
        *,
        channel_no: int = 1,
        quality: Literal["high", "fluent"] = "high",
    ) -> StreamPlayback:
        device = await self.device_service.get_device(device_serial)
        if device.online is False:
            from app.adapters.ezviz.exceptions import EzvizDeviceOfflineError

            raise EzvizDeviceOfflineError("EZVIZ device is offline")

        adapter = self._require_adapter()
        stream = await adapter.get_hls_preview(
            device_serial,
            channel_no=channel_no,
            quality=1 if quality == "high" else 2,
        )
        return StreamPlayback(
            device_id=device.id,
            channel_no=channel_no,
            playback_url=str(stream["playback_url"]),
            expires_at=stream["expires_at"],
            quality=quality,
        )

    def _require_adapter(self) -> EzvizStreamAdapter:
        if self.adapter is not None:
            return self.adapter
        if not self.device_service.settings.configured or self.device_service.client is None:
            raise EzvizNotConfiguredError("EZVIZ integration is not configured")
        self.adapter = EzvizStreamAdapter(self.device_service.client)
        return self.adapter
