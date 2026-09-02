import asyncio
import threading

import httpx

from app.adapters.backend_media import BackendMediaClient, RelayMediaError
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


def test_relay_builds_low_latency_h264_output() -> None:
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

    class CodecContext:
        width = 1280
        height = 720
        gop_size = None
        max_b_frames = None

    class InputVideo:
        average_rate = 15
        codec_context = CodecContext()

    class OutputVideo:
        codec_context = CodecContext()
        width = None
        height = None
        pix_fmt = None
        options = None

    class Output:
        def add_stream(self, codec, *, rate):
            assert codec == "libx264"
            assert rate == 15
            return OutputVideo()

    result = service._create_output_video(Output(), InputVideo())

    assert result.width == 1280
    assert result.height == 720
    assert result.pix_fmt == "yuv420p"
    assert result.options["preset"] == "ultrafast"
    assert result.options["tune"] == "zerolatency"
    assert result.codec_context.gop_size == 15
    assert result.codec_context.max_b_frames == 0
    asyncio.run(service.close())


def test_relay_starts_publishing_on_first_video_keyframe(monkeypatch) -> None:
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

    class Stream:
        def __init__(self, stream_type):
            self.type = stream_type

    class Frame:
        def __init__(self, name, *, keyframe=False, corrupt=False):
            self.name = name
            self.key_frame = keyframe
            self.is_corrupt = corrupt

    class Packet:
        def __init__(self, name, stream, *, frame=None):
            self.name = name
            self.stream = stream
            self.dts = 1

            self.frame = frame

        def decode(self):
            return [self.frame] if self.frame is not None else []

    video = Stream("video")
    audio = Stream("audio")
    packets = [
        Packet("p-before-idr", video, frame=Frame("p-before-idr")),
        Packet("audio-before-idr", audio),
        Packet("first-idr", video, frame=Frame("first-idr", keyframe=True)),
        Packet("audio-after-idr", audio),
        Packet("p-after-idr", video, frame=Frame("p-after-idr")),
    ]

    class Source:
        streams = [video, audio]

        def demux(self, streams):
            return iter(packets)

        def close(self):
            pass

    class Output:
        def __init__(self):
            self.written = []

        def add_stream_from_template(self, stream):
            return Stream(stream.type)

        def mux(self, packet):
            self.written.append(packet.name)

        def close(self):
            pass

    class Encoder:
        def encode(self, frame=None):
            return [] if frame is None else [Packet(frame.name, self)]

    source = Source()
    output = Output()
    monkeypatch.setattr(
        "app.services.relay.av.open",
        lambda url, **kwargs: output if kwargs.get("mode") == "w" else source,
    )
    monkeypatch.setattr(service, "_create_output_video", lambda *args: Encoder())

    service._transcode("https://temporary.invalid/live.flv", threading.Event())

    assert output.written == ["first-idr", "audio-after-idr", "p-after-idr"]
    asyncio.run(service.close())


def test_publisher_failure_during_cleanup_does_not_escape() -> None:
    async def run() -> None:
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

        async def fail_while_stopping() -> None:
            await asyncio.sleep(0)
            raise RelayMediaError("Media publisher failed")

        service._publisher_stop = threading.Event()
        service._publisher_task = asyncio.create_task(fail_while_stopping())
        await service._stop_publisher()

        assert service._publisher_task is None
        assert service._publisher_stop is None
        await service.client.close()
        await service._media_server.aclose()

    asyncio.run(run())


def test_timed_out_publisher_cleanup_retrieves_late_failure(monkeypatch) -> None:
    async def run() -> None:
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
        release = asyncio.Event()

        async def fail_later() -> None:
            await release.wait()
            raise RuntimeError("temporary-url-must-not-be-logged")

        async def immediate_timeout(*args, **kwargs):
            raise asyncio.TimeoutError

        monkeypatch.setattr("app.services.relay.asyncio.wait_for", immediate_timeout)
        task = asyncio.create_task(fail_later())
        service._publisher_stop = threading.Event()
        service._publisher_task = task
        await service._stop_publisher()

        release.set()
        await asyncio.sleep(0)
        # Task completion and its done callback occupy separate event-loop turns
        # on Python 3.13.
        await asyncio.sleep(0)
        assert task.done()
        # The registered callback calls task.result() and consumes the failure.
        assert task._log_traceback is False
        await service.client.close()
        await service._media_server.aclose()

    asyncio.run(run())
