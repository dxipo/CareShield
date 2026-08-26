import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.adapters.ezviz.client import EzvizClient
from app.adapters.ezviz.exceptions import (
    EzvizApiError,
    EzvizDeviceNotFoundError,
    EzvizDeviceOfflineError,
    EzvizStreamUnavailableError,
)
from app.adapters.ezviz.stream import EzvizStreamAdapter
from app.core.config import EzvizSettings
from app.schemas.device import DeviceDetail
from app.services.stream_service import StreamService


class FakeStreamClient:
    def __init__(self, payload: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def get_live_address(self, device_serial: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"device_serial": device_serial, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.payload is not None
        return self.payload


class FakeDeviceService:
    def __init__(
        self,
        *,
        online: bool = True,
        missing: bool = False,
        browser_enabled: bool = False,
        client: object | None = None,
    ) -> None:
        self.online = online
        self.missing = missing
        self.settings = EzvizSettings(
            "example-key",
            "example-secret",
            browser_playback_enabled=browser_enabled,
        )
        self.client = client

    async def get_device(self, device_serial: str) -> DeviceDetail:
        if self.missing:
            raise EzvizDeviceNotFoundError("not found")
        return DeviceDetail(
            id="ezviz_safeid",
            device_serial=device_serial,
            status="online" if self.online else "offline",
            online=self.online,
        )


def test_stream_response_mapping_and_request_parameters(caplog: pytest.LogCaptureFixture) -> None:
    playback_url = "https://example.invalid/live.m3u8?sensitive=temporary"
    client = FakeStreamClient(
        {
            "code": "200",
            "data": {
                "id": "provider-stream-id",
                "url": playback_url,
                "expireTime": "2026-08-16 13:00:00",
            },
        }
    )
    adapter = EzvizStreamAdapter(client)  # type: ignore[arg-type]
    service = StreamService(FakeDeviceService(), adapter)  # type: ignore[arg-type]

    with caplog.at_level(logging.DEBUG):
        stream = asyncio.run(
            service.get_live_stream("TEST123456", channel_no=1, quality="high")
        )

    assert stream.device_id == "ezviz_safeid"
    assert stream.protocol == "hls"
    assert stream.playback_url == playback_url
    assert stream.expires_at == "2026-08-16 13:00:00"
    assert stream.requested_video_codec == "h265"
    assert stream.container == "mpeg-ts"
    assert stream.muted is False
    assert client.calls == [
        {
            "device_serial": "TEST123456",
            "channel_no": 1,
            "quality": 1,
            "expire_seconds": 3600,
            "support_h265": True,
            "container_format": 0,
            "mute": False,
        }
    ]
    assert playback_url not in caplog.text


def test_live_address_posts_h265_ts_and_unmuted_parameters() -> None:
    observed_form: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/lapp/token/get":
            return httpx.Response(
                200,
                json={
                    "code": "200",
                    "data": {
                        "accessToken": "test-token",
                        "expireTime": 4_000_000_000_000,
                    },
                },
            )
        observed_form.update(parse_qs(request.content.decode()))
        return httpx.Response(
            200,
            json={"code": "200", "data": {"url": "https://example.invalid/live.m3u8"}},
        )

    async def scenario() -> None:
        client = EzvizClient(
            EzvizSettings("example-key", "example-secret"),
            transport=httpx.MockTransport(handler),
        )
        try:
            await client.get_live_address(
                "TEST123456",
                channel_no=1,
                quality=1,
                expire_seconds=3600,
                support_h265=True,
                container_format=0,
                mute=False,
            )
        finally:
            await client.close()

    asyncio.run(scenario())

    assert observed_form["protocol"] == ["2"]
    assert observed_form["quality"] == ["1"]
    assert observed_form["channelNo"] == ["1"]
    assert observed_form["expireTime"] == ["3600"]
    assert observed_form["supportH265"] == ["1"]
    assert observed_form["containerFormat"] == ["0"]
    assert observed_form["mute"] == ["0"]


def test_missing_device_is_preserved() -> None:
    service = StreamService(FakeDeviceService(missing=True))  # type: ignore[arg-type]

    with pytest.raises(EzvizDeviceNotFoundError):
        asyncio.run(service.get_live_stream("MISSING"))


def test_offline_device_does_not_request_stream() -> None:
    client = FakeStreamClient({"code": "200", "data": {"url": "https://example.invalid/live.m3u8"}})
    service = StreamService(
        FakeDeviceService(online=False),  # type: ignore[arg-type]
        EzvizStreamAdapter(client),  # type: ignore[arg-type]
    )

    with pytest.raises(EzvizDeviceOfflineError):
        asyncio.run(service.get_live_stream("OFFLINE"))
    assert client.calls == []


def test_ezviz_stream_api_error_is_safely_mapped() -> None:
    secret = "must-not-leak"
    client = FakeStreamClient(error=EzvizApiError("60019"))
    adapter = EzvizStreamAdapter(client)  # type: ignore[arg-type]

    with pytest.raises(EzvizStreamUnavailableError) as error:
        asyncio.run(
            adapter.get_hls_preview(
                "TEST123456",
                channel_no=1,
                quality=1,
            )
        )

    assert error.value.code == "60019"
    assert secret not in str(error.value)


class FakeTokenManager:
    async def get_access_token(self) -> str:
        return "runtime-token"


class FakeBrowserClient:
    token_manager = FakeTokenManager()


def test_ezopen_browser_session_mapping() -> None:
    service = StreamService(
        FakeDeviceService(
            browser_enabled=True,
            client=FakeBrowserClient(),
        )  # type: ignore[arg-type]
    )

    session = asyncio.run(
        service.get_browser_playback_session("TEST SERIAL", channel_no=2)
    )

    assert session.protocol == "ezopen"
    assert session.playback_url == "ezopen://open.ys7.com/TEST%20SERIAL/2.live"
    assert session.access_token == "runtime-token"
    assert session.decoder == "v3"
    assert session.quality == "performance"


def test_ezopen_browser_session_requires_explicit_enablement() -> None:
    from app.adapters.ezviz.exceptions import EzvizBrowserPlaybackDisabledError

    service = StreamService(FakeDeviceService())  # type: ignore[arg-type]

    with pytest.raises(EzvizBrowserPlaybackDisabledError):
        asyncio.run(service.get_browser_playback_session("TEST123456"))
