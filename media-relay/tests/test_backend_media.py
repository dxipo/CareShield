import asyncio

import httpx

from app.adapters.backend_media import BackendMediaClient
from app.core.config import RelaySettings
from app.services.relay import RelayService


def test_relay_requests_single_http_flv_source_without_exposing_credentials() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/devices"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "safe-device",
                            "device_serial": "TEST-SERIAL",
                            "online": True,
                        }
                    ],
                )
            return httpx.Response(
                200,
                json={
                    "device_id": "safe-device",
                    "playback_url": "https://temporary.invalid/live.flv",
                },
            )

        client = BackendMediaClient(
            "http://backend.test",
            "test-token",
            1,
            transport=httpx.MockTransport(handler),
        )
        try:
            device = await client.select_device()
            source = await client.get_http_flv(device)
        finally:
            await client.close()

        assert source.device_id == "safe-device"
        assert requests[-1].url.params["protocol"] == "http_flv"
        assert all(req.headers["authorization"] == "Bearer test-token" for req in requests)

    asyncio.run(run())


def test_relay_converts_hevc_to_annex_b_without_transcoding(monkeypatch) -> None:
    service = RelayService(
        RelaySettings(
            backend_internal_url="http://backend.test",
            shared_token="test-token",
            channel_no=1,
            publish_url="rtsp://media.test/careshield",
            public_read_url="rtsp://media.test/careshield",
            media_server_api_url="http://media.test",
            reconnect_seconds=1.0,
        )
    )

    captured: dict[str, object] = {}

    def fake_filter(name, input_stream, output_stream):
        captured.update(
            name=name,
            input_stream=input_stream,
            output_stream=output_stream,
        )
        return object()

    monkeypatch.setattr(
        "app.services.relay.av.bitstream.BitStreamFilterContext",
        fake_filter,
    )
    input_stream = object()
    output_stream = object()
    result = service._create_video_filter(input_stream, output_stream)

    assert result is not None
    assert captured == {
        "name": "hevc_mp4toannexb",
        "input_stream": input_stream,
        "output_stream": output_stream,
    }
    asyncio.run(service.close())
