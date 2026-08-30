from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class RelayMediaError(RuntimeError):
    """A safe Backend media failure without response bodies or stream URLs."""


@dataclass(frozen=True, slots=True)
class RelayDevice:
    id: str
    serial: str


@dataclass(frozen=True, slots=True)
class RelaySource:
    device_id: str
    playback_url: str


class BackendMediaClient:
    def __init__(
        self,
        base_url: str,
        shared_token: str,
        channel_no: int,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._channel_no = channel_no
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {shared_token}"},
            timeout=15.0,
            trust_env=False,
            transport=transport,
        )

    async def select_device(self) -> RelayDevice:
        response = await self._get("/internal/media/devices")
        payload = self._json(response)
        if not isinstance(payload, list):
            raise RelayMediaError("Backend device response is invalid")
        for item in payload:
            if not isinstance(item, dict) or item.get("online") is not True:
                continue
            device_id = item.get("id")
            serial = item.get("device_serial")
            if isinstance(device_id, str) and isinstance(serial, str):
                return RelayDevice(id=device_id, serial=serial)
        raise RelayMediaError("No online camera is available for relay")

    async def get_http_flv(self, device: RelayDevice) -> RelaySource:
        response = await self._get(
            f"/internal/media/devices/{quote(device.serial, safe='')}/stream",
            params={
                "channel_no": self._channel_no,
                "quality": "high",
                "protocol": "http_flv",
            },
        )
        payload = self._json(response)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("playback_url"), str
        ):
            raise RelayMediaError("Backend stream response is invalid")
        return RelaySource(
            device_id=str(payload.get("device_id", device.id)),
            playback_url=payload["playback_url"],
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.get(path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise RelayMediaError("Backend media service is unavailable") from exc

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise RelayMediaError("Backend media response is invalid") from exc
