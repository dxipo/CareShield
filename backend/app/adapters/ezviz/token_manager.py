import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.adapters.ezviz.exceptions import (
    EzvizApiError,
    EzvizNetworkError,
    EzvizNotConfiguredError,
    EzvizResponseError,
)
from app.core.config import EzvizSettings


@dataclass(frozen=True, slots=True)
class EzvizToken:
    value: str
    expire_time_ms: int


class EzvizTokenManager:
    def __init__(
        self,
        settings: EzvizSettings,
        http_client: httpx.AsyncClient,
        *,
        refresh_margin_ms: int = 5 * 60 * 1000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._refresh_margin_ms = refresh_margin_ms
        self._clock = clock
        self._token: EzvizToken | None = None
        self._lock = asyncio.Lock()

    async def get_access_token(self, *, force_refresh: bool = False) -> str:
        if not self._settings.configured:
            raise EzvizNotConfiguredError("EZVIZ integration is not configured")

        if not force_refresh and self._is_cached_token_valid():
            return self._token.value  # type: ignore[union-attr]

        async with self._lock:
            if not force_refresh and self._is_cached_token_valid():
                return self._token.value  # type: ignore[union-attr]

            self._token = await self._request_token()
            return self._token.value

    def invalidate(self) -> None:
        self._token = None

    def _is_cached_token_valid(self) -> bool:
        if self._token is None:
            return False
        now_ms = int(self._clock() * 1000)
        return now_ms + self._refresh_margin_ms < self._token.expire_time_ms

    async def _request_token(self) -> EzvizToken:
        try:
            response = await self._http_client.post(
                "/api/lapp/token/get",
                data={
                    "appKey": self._settings.app_key,
                    "appSecret": self._settings.app_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EzvizNetworkError("Unable to reach EZVIZ Open API") from exc

        payload = self._parse_payload(response)
        code = str(payload.get("code", ""))
        if code != "200":
            raise EzvizApiError(code or None)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise EzvizResponseError("EZVIZ token response has no data object")

        access_token = data.get("accessToken")
        expire_time = data.get("expireTime")
        if not isinstance(access_token, str) or not access_token:
            raise EzvizResponseError("EZVIZ token response has no access token")

        try:
            expire_time_ms = int(expire_time)
        except (TypeError, ValueError) as exc:
            raise EzvizResponseError("EZVIZ token expiration is invalid") from exc

        return EzvizToken(value=access_token, expire_time_ms=expire_time_ms)

    @staticmethod
    def _parse_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise EzvizResponseError("EZVIZ returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EzvizResponseError("EZVIZ returned an invalid response")
        return payload
