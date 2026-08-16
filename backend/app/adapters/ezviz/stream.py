from typing import Any

from app.adapters.ezviz.client import EzvizClient
from app.adapters.ezviz.exceptions import (
    EzvizApiError,
    EzvizDeviceNotFoundError,
    EzvizDeviceOfflineError,
    EzvizResponseError,
    EzvizStreamUnavailableError,
)


class EzvizStreamAdapter:
    """Maps EZVIZ live-address responses into a small internal contract."""

    def __init__(self, client: EzvizClient) -> None:
        self.client = client

    async def get_hls_preview(
        self,
        device_serial: str,
        *,
        channel_no: int,
        quality: int,
        expire_seconds: int = 3600,
    ) -> dict[str, str | None]:
        try:
            payload = await self.client.get_live_address(
                device_serial,
                channel_no=channel_no,
                quality=quality,
                expire_seconds=expire_seconds,
            )
        except EzvizApiError as exc:
            if exc.code in {"20001", "20002"}:
                raise EzvizDeviceNotFoundError(
                    "EZVIZ device or channel was not found"
                ) from exc
            if exc.code == "20007":
                raise EzvizDeviceOfflineError("EZVIZ device is offline") from exc
            raise EzvizStreamUnavailableError(exc.code) from exc

        data = payload.get("data")
        if not isinstance(data, dict):
            raise EzvizResponseError("EZVIZ stream response data is invalid")

        playback_url = self._non_empty_string(data.get("url"))
        if playback_url is None:
            raise EzvizResponseError("EZVIZ stream response has no playback URL")

        return {
            "playback_url": playback_url,
            "provider_stream_id": self._non_empty_string(data.get("id")),
            "expires_at": self._optional_text(data.get("expireTime")),
        }

    @staticmethod
    def _non_empty_string(value: Any) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)
