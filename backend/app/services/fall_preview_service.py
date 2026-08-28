from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from app.core.config import AiRealtimeSettings


class FallPreviewUnavailableError(RuntimeError):
    pass


class FallPreviewService:
    """Relay an authenticated in-memory Worker preview without persisting frames."""

    def __init__(self, settings: AiRealtimeSettings) -> None:
        self._settings = settings

    async def stream(self) -> AsyncIterator[bytes]:
        headers = {"Authorization": f"Bearer {self._settings.shared_token}"}
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.worker_internal_url,
                headers=headers,
                timeout=httpx.Timeout(connect=5, read=None, write=5, pool=5),
                trust_env=False,
            ) as client:
                async with client.stream(
                    "GET",
                    "/internal/fall-detection/preview.mjpeg",
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_raw():
                        yield chunk
        except httpx.HTTPError as exc:
            raise FallPreviewUnavailableError("AI analysis preview is unavailable") from exc

    async def acknowledge_alert(self) -> dict[str, bool]:
        headers = {"Authorization": f"Bearer {self._settings.shared_token}"}
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.worker_internal_url,
                headers=headers,
                timeout=5,
                trust_env=False,
            ) as client:
                response = await client.post(
                    "/internal/fall-detection/alert/acknowledge"
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise FallPreviewUnavailableError("Fall alert could not be acknowledged") from exc
