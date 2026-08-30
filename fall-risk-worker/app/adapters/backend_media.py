from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class MediaAccessError(RuntimeError):
    """Safe media error that never includes credentials or playback URLs."""


@dataclass(frozen=True, slots=True)
class MediaDevice:
    id: str
    serial: str
    online: bool | None


@dataclass(frozen=True, slots=True)
class TemporaryStream:
    device_id: str
    playback_url: str
    protocol: str


class BackendMediaClient:
    def __init__(
        self,
        base_url: str,
        shared_token: str,
        channel_no: int,
        *,
        relay_base_url: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._channel_no = channel_no
        self._relay_client = (
            httpx.AsyncClient(
                base_url=relay_base_url,
                headers={"Authorization": f"Bearer {shared_token}"},
                timeout=10.0,
                trust_env=False,
                transport=transport,
            )
            if relay_base_url
            else None
        )
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {shared_token}"},
            timeout=15.0,
            trust_env=False,
            transport=transport,
        )

    async def select_device(self, preferred_id: str | None) -> MediaDevice:
        response = await self._get("/internal/media/devices")
        payload = response.json()
        if not isinstance(payload, list):
            raise MediaAccessError("Backend device response is invalid")
        devices = [self._map_device(item) for item in payload if isinstance(item, dict)]
        selected = (
            next((device for device in devices if device.id == preferred_id), None)
            if preferred_id
            else next((device for device in devices if device.online is True), None)
        )
        if selected is None:
            raise MediaAccessError("No matching online camera is available")
        if selected.online is not True:
            raise MediaAccessError("Selected camera is offline")
        return selected

    async def get_stream(self, device: MediaDevice) -> TemporaryStream:
        relay = await self._get_relay_stream()
        if relay is not None:
            return relay
        response = await self._get(
            f"/internal/media/devices/{quote(device.serial, safe='')}/stream",
            params={
                "channel_no": self._channel_no,
                "quality": "high",
                "protocol": "hls",
            },
        )
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("playback_url"), str):
            raise MediaAccessError("Backend stream response is invalid")
        return TemporaryStream(
            device_id=str(payload.get("device_id", device.id)),
            playback_url=payload["playback_url"],
            protocol=str(payload.get("protocol", "unknown")),
        )

    async def close(self) -> None:
        await self._client.aclose()
        if self._relay_client is not None:
            await self._relay_client.aclose()

    async def _get_relay_stream(self) -> TemporaryStream | None:
        if self._relay_client is None:
            return None
        try:
            response = await self._relay_client.get("/stream")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("ready") is not True:
            return None
        playback_url = payload.get("playback_url")
        if not isinstance(playback_url, str) or not playback_url.startswith("rtsp://"):
            return None
        return TemporaryStream(
            device_id=str(payload.get("device_id", "")),
            playback_url=playback_url,
            protocol="rtsp",
        )

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.get(path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise MediaAccessError("Backend media service is unavailable") from exc

    @staticmethod
    def _map_device(payload: dict[str, Any]) -> MediaDevice:
        if not isinstance(payload.get("id"), str) or not isinstance(
            payload.get("device_serial"), str
        ):
            raise MediaAccessError("Backend device response is invalid")
        return MediaDevice(
            id=payload["id"],
            serial=payload["device_serial"],
            online=payload.get("online") if isinstance(payload.get("online"), bool) else None,
        )
