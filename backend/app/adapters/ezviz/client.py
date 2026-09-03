from typing import Any

import httpx

from app.adapters.ezviz.exceptions import (
    EzvizApiError,
    EzvizDeviceNotFoundError,
    EzvizNetworkError,
    EzvizResponseError,
    EzvizVoiceQuotaError,
)
from app.adapters.ezviz.token_manager import EzvizTokenManager
from app.core.config import EzvizSettings


class EzvizClient:
    def __init__(
        self,
        settings: EzvizSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        token_manager: EzvizTokenManager | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=settings.timeout_seconds,
            transport=transport,
        )
        self.token_manager = token_manager or EzvizTokenManager(
            settings,
            self._http_client,
        )

    async def close(self) -> None:
        await self._http_client.aclose()

    async def list_devices_page(
        self,
        *,
        page_start: int = 0,
        page_size: int = 50,
    ) -> dict[str, Any]:
        return await self._authorized_post(
            "/api/lapp/device/list",
            {"pageStart": page_start, "pageSize": page_size},
        )

    async def list_all_devices(self) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []

        for page_start in range(401):
            payload = await self.list_devices_page(
                page_start=page_start,
                page_size=50,
            )
            page_data = payload.get("data")
            if not isinstance(page_data, list):
                raise EzvizResponseError("EZVIZ device list data is invalid")

            devices.extend(item for item in page_data if isinstance(item, dict))

            page = payload.get("page")
            total = page.get("total") if isinstance(page, dict) else None
            if isinstance(total, int) and len(devices) >= total:
                break
            if len(page_data) < 50:
                break

        return devices

    async def get_device_info(self, device_serial: str) -> dict[str, Any] | None:
        try:
            payload = await self._authorized_post(
                "/api/lapp/device/info",
                {"deviceSerial": device_serial},
            )
        except EzvizApiError as exc:
            if exc.code == "10001":
                raise EzvizDeviceNotFoundError("EZVIZ device was not found") from exc
            raise
        data = payload.get("data")
        if data is None:
            return None
        if not isinstance(data, dict):
            raise EzvizResponseError("EZVIZ device detail data is invalid")
        return data

    async def get_device_capacity(
        self,
        device_serial: str,
        *,
        channel_no: int = 1,
    ) -> dict[str, Any]:
        payload = await self._authorized_post(
            "/api/lapp/device/capacity",
            {"deviceSerial": device_serial, "channelNo": channel_no},
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise EzvizResponseError("EZVIZ device capacity data is invalid")
        return data

    async def send_voice_once(
        self,
        device_serial: str,
        *,
        channel_no: int,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> None:
        """Send one transient audio file without exposing the access token."""

        try:
            await self._authorized_multipart_post(
                "/api/lapp/voice/sendonce",
                {"deviceSerial": device_serial, "channelNo": str(channel_no)},
                {"voiceFile": (filename, content, content_type)},
            )
        except EzvizApiError as exc:
            if exc.code == "111000":
                raise EzvizVoiceQuotaError(
                    "EZVIZ voice broadcast quota is unavailable"
                ) from exc
            raise

    async def get_live_address(
        self,
        device_serial: str,
        *,
        channel_no: int,
        quality: int,
        expire_seconds: int,
        support_h265: bool,
        container_format: int | None,
        mute: bool,
        protocol: int = 2,
    ) -> dict[str, Any]:
        """Request a temporary standard preview address from EZVIZ.

        H.265 capability is deliberately explicit. For HLS, an omitted
        container can make the endpoint return a decodable compatibility
        notice instead of the camera stream. HTTP-FLV does not use that HLS
        container option.
        """
        request_data = {
            "deviceSerial": device_serial,
            "channelNo": channel_no,
            "protocol": protocol,
            "type": 1,
            "quality": quality,
            "expireTime": expire_seconds,
            "supportH265": int(support_h265),
            "mute": int(mute),
        }
        if container_format is not None:
            request_data["containerFormat"] = container_format
        return await self._authorized_post(
            "/api/lapp/v2/live/address/get",
            request_data,
        )

    async def check_reachable(self) -> None:
        await self.list_devices_page(page_start=0, page_size=1)

    async def _authorized_post(
        self,
        path: str,
        data: dict[str, Any],
        *,
        retry_token: bool = True,
    ) -> dict[str, Any]:
        access_token = await self.token_manager.get_access_token()
        payload = await self._post(
            path,
            {"accessToken": access_token, **data},
        )
        code = str(payload.get("code", ""))

        if code == "10002" and retry_token:
            self.token_manager.invalidate()
            await self.token_manager.get_access_token(force_refresh=True)
            return await self._authorized_post(path, data, retry_token=False)

        if code != "200":
            raise EzvizApiError(code or None)
        return payload

    async def _authorized_multipart_post(
        self,
        path: str,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
        *,
        retry_token: bool = True,
    ) -> dict[str, Any]:
        access_token = await self.token_manager.get_access_token()
        try:
            response = await self._http_client.post(
                path,
                data={"accessToken": access_token, **data},
                files=files,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EzvizNetworkError("Unable to reach EZVIZ Open API") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise EzvizResponseError("EZVIZ returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EzvizResponseError("EZVIZ returned an invalid response")

        code = str(payload.get("code", ""))
        if code == "10002" and retry_token:
            self.token_manager.invalidate()
            await self.token_manager.get_access_token(force_refresh=True)
            return await self._authorized_multipart_post(
                path,
                data,
                files,
                retry_token=False,
            )
        if code != "200":
            raise EzvizApiError(code or None)
        return payload

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._http_client.post(path, data=data)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EzvizNetworkError("Unable to reach EZVIZ Open API") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise EzvizResponseError("EZVIZ returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EzvizResponseError("EZVIZ returned an invalid response")
        return payload
