import asyncio
import json

import httpx

from app.core.config import WorkerSettings
from app.media.backend_client import BackendMediaClient, MediaBackendError


def settings() -> WorkerSettings:
    return WorkerSettings(
        app_env="development",
        backend_internal_url="http://backend.test",
        shared_token="internal-test-token",
        worker_id="worker-test",
        worker_version="0.5.0",
        heartbeat_interval_seconds=10,
        request_timeout_seconds=5,
    )


def test_worker_gets_standard_device_and_temporary_stream_with_internal_auth() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/devices"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "ezviz_safe_id",
                            "device_serial": "TEST-SERIAL",
                            "name": "Camera",
                            "model": "H6c",
                            "online": True,
                            "status": "online",
                            "provider": "ezviz",
                            "camera_count": 1,
                            "channels": [],
                            "updated_at": None,
                            "device_type": "camera",
                        }
                    ],
                )
            return httpx.Response(
                200,
                json={
                    "device_id": "ezviz_safe_id",
                    "channel_no": 1,
                    "protocol": "hls",
                    "playback_url": "https://temporary.invalid/live.m3u8?secret=runtime",
                    "expires_at": None,
                    "quality": "high",
                    "requested_video_codec": "h265",
                    "container": "mpeg-ts",
                    "muted": False,
                },
            )

        client = BackendMediaClient(settings(), transport=httpx.MockTransport(handler))
        try:
            device = await client.select_device()
            stream = await client.get_stream(device.serial)
        finally:
            await client.close()

        assert device.id == "ezviz_safe_id"
        assert stream.protocol == "hls"
        assert all(
            request.headers["authorization"] == "Bearer internal-test-token"
            for request in requests
        )

    asyncio.run(run())


def test_backend_error_does_not_expose_response_or_runtime_url() -> None:
    async def run() -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                502,
                content=json.dumps({"detail": "https://private.invalid/stream?token=secret"}),
            )

        client = BackendMediaClient(settings(), transport=httpx.MockTransport(handler))
        try:
            try:
                await client.select_device()
            except MediaBackendError as exc:
                message = str(exc)
            else:
                raise AssertionError("expected MediaBackendError")
        finally:
            await client.close()

        assert "private.invalid" not in message
        assert "secret" not in message
        assert "502" in message

    asyncio.run(run())
