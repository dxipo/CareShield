from typing import Literal
from urllib.parse import quote

from app.adapters.ezviz.exceptions import (
    EzvizBrowserPlaybackDisabledError,
    EzvizDeviceOfflineError,
    EzvizNotConfiguredError,
)
from app.adapters.ezviz.stream import EzvizStreamAdapter
from app.schemas.stream import BrowserPlaybackSession, StreamPlayback
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
            raise EzvizDeviceOfflineError("EZVIZ device is offline")

        adapter = self._require_adapter()
        stream = await adapter.get_hls_preview(
            device_serial,
            channel_no=channel_no,
            quality=1 if quality == "high" else 2,
            support_h265=True,
            container_format=0,
            mute=False,
        )
        return StreamPlayback(
            device_id=device.id,
            channel_no=channel_no,
            playback_url=str(stream["playback_url"]),
            expires_at=stream["expires_at"],
            quality=quality,
            requested_video_codec="h265",
            container="mpeg-ts",
            muted=False,
        )

    async def get_browser_playback_session(
        self,
        device_serial: str,
        *,
        channel_no: int = 1,
    ) -> BrowserPlaybackSession:
        """Create a no-store EZOPEN session for the official browser SDK.

        The official SDK requires both the EZOPEN URL and AccessToken in the
        browser. This method deliberately keeps that exception separate from
        the standard HLS contract consumed by ffprobe and the AI Worker.
        """
        settings = self.device_service.settings
        if not settings.browser_playback_enabled:
            raise EzvizBrowserPlaybackDisabledError(
                "EZVIZ browser playback is disabled"
            )

        device = await self.device_service.get_device(device_serial)
        if device.online is False:
            raise EzvizDeviceOfflineError("EZVIZ device is offline")

        client = self.device_service.client
        if client is None:
            raise EzvizNotConfiguredError("EZVIZ integration is not configured")

        access_token = await client.token_manager.get_access_token()
        safe_serial = quote(device_serial, safe="")
        safe_domain = settings.ezopen_domain.strip().strip("/")
        playback_url = f"ezopen://{safe_domain}/{safe_serial}/{channel_no}.live"
        return BrowserPlaybackSession(
            device_id=device.id,
            channel_no=channel_no,
            playback_url=playback_url,
            access_token=access_token,
        )

    def _require_adapter(self) -> EzvizStreamAdapter:
        if self.adapter is not None:
            return self.adapter
        if not self.device_service.settings.configured or self.device_service.client is None:
            raise EzvizNotConfiguredError("EZVIZ integration is not configured")
        self.adapter = EzvizStreamAdapter(self.device_service.client)
        return self.adapter
