from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import WorkerSettings


class MediaBackendError(RuntimeError):
    """Safe error that excludes credentials, response bodies, and playback URLs."""


@dataclass(frozen=True, slots=True)
class MediaDevice:
    id: str
    serial: str
    name: str | None
    model: str | None
    online: bool | None


@dataclass(frozen=True, slots=True)
class TemporaryStream:
    playback_url: str
    device_id: str
    channel_no: int
    protocol: str
    expires_at: str | None


class BackendMediaClient:
    def __init__(
        self,
        settings: WorkerSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._preferred_serial = settings.fall_device_serial
        self._channel_no = settings.fall_channel_no
        self._relay_client = (
            httpx.AsyncClient(
                base_url=settings.media_relay_internal_url,
                headers={"Authorization": f"Bearer {settings.shared_token}"},
                timeout=settings.media_request_timeout_seconds,
                transport=transport,
                trust_env=False,
            )
            if settings.media_relay_internal_url
            else None
        )
        self._client = httpx.AsyncClient(
            base_url=settings.backend_internal_url,
            headers={"Authorization": f"Bearer {settings.shared_token}"},
            timeout=settings.media_request_timeout_seconds,
            transport=transport,
            trust_env=False,
        )

    async def select_device(self) -> MediaDevice:
        response = await self._get("/internal/media/devices")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaBackendError("Backend media device response is invalid") from exc
        if not isinstance(payload, list):
            raise MediaBackendError("Backend media device response is invalid")

        devices = [self._map_device(item) for item in payload if isinstance(item, dict)]
        if self._preferred_serial:
            selected = next(
                (device for device in devices if device.serial == self._preferred_serial),
                None,
            )
            if selected is None:
                raise MediaBackendError("Configured fall-detection device was not found")
        else:
            selected = next((device for device in devices if device.online is True), None)
        if selected is None:
            raise MediaBackendError("No online media device is available")
        if selected.online is not True:
            raise MediaBackendError("Configured fall-detection device is offline")
        return selected

    async def get_stream(self, device_serial: str) -> TemporaryStream:
        relay = await self._get_relay_stream()
        if relay is not None:
            return relay
        encoded_serial = quote(device_serial, safe="")
        response = await self._get(
            f"/internal/media/devices/{encoded_serial}/stream",
            params={
                "channel_no": self._channel_no,
                "quality": "high",
                "protocol": "http_flv",
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaBackendError("Backend temporary stream response is invalid") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("playback_url"), str):
            raise MediaBackendError("Backend temporary stream response is invalid")
        return TemporaryStream(
            playback_url=payload["playback_url"],
            device_id=str(payload.get("device_id", "")),
            channel_no=int(payload.get("channel_no", self._channel_no)),
            protocol=str(payload.get("protocol", "hls")),
            expires_at=(
                str(payload["expires_at"]) if payload.get("expires_at") is not None else None
            ),
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
            playback_url=playback_url,
            device_id=str(payload.get("device_id", "")),
            channel_no=self._channel_no,
            protocol="rtsp",
            expires_at=None,
        )

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.get(path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise MediaBackendError(
                f"Backend media request failed with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise MediaBackendError("Backend media service is unreachable") from exc

    @staticmethod
    def _map_device(payload: dict[str, Any]) -> MediaDevice:
        serial = payload.get("device_serial")
        device_id = payload.get("id")
        if not isinstance(serial, str) or not isinstance(device_id, str):
            raise MediaBackendError("Backend media device response is invalid")
        return MediaDevice(
            id=device_id,
            serial=serial,
            name=payload.get("name") if isinstance(payload.get("name"), str) else None,
            model=payload.get("model") if isinstance(payload.get("model"), str) else None,
            online=payload.get("online") if isinstance(payload.get("online"), bool) else None,
        )
