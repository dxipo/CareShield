import asyncio

import httpx

from app.adapters.backend_media import BackendMediaClient, MediaDevice


def test_batch_assessment_explicitly_requests_hls() -> None:
    async def run() -> None:
        captured: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={
                    "device_id": "safe-device-id",
                    "channel_no": 1,
                    "protocol": "hls",
                    "playback_url": "https://temporary.invalid/live.m3u8",
                    "expires_at": None,
                    "quality": "high",
                    "container": "mpeg-ts",
                },
            )

        client = BackendMediaClient(
            "http://backend.test",
            "internal-test-token",
            1,
            transport=httpx.MockTransport(handler),
        )
        try:
            stream = await client.get_stream(
                MediaDevice(id="safe-device-id", serial="TEST-SERIAL", online=True)
            )
        finally:
            await client.close()

        assert stream.protocol == "hls"
        assert captured[0].url.params["protocol"] == "hls"
        assert captured[0].headers["authorization"] == "Bearer internal-test-token"

    asyncio.run(run())


def test_batch_assessment_prefers_ready_shared_rtsp_relay() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.host == "relay.test":
                return httpx.Response(
                    200,
                    json={
                        "ready": True,
                        "device_id": "safe-device-id",
                        "playback_url": "rtsp://media-server:8554/careshield",
                    },
                )
            raise AssertionError("HLS fallback should not be requested")

        client = BackendMediaClient(
            "http://backend.test",
            "internal-test-token",
            1,
            relay_base_url="http://relay.test",
            transport=httpx.MockTransport(handler),
        )
        try:
            stream = await client.get_stream(
                MediaDevice(id="safe-device-id", serial="TEST-SERIAL", online=True)
            )
        finally:
            await client.close()

        assert stream.protocol == "rtsp"
        assert stream.playback_url == "rtsp://media-server:8554/careshield"
        assert requests[0].headers["authorization"] == "Bearer internal-test-token"

    asyncio.run(run())
