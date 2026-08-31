from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import av

from app.adapters.backend_media import BackendMediaClient, RelayMediaError
from app.core.config import RelaySettings


@dataclass(frozen=True, slots=True)
class RelaySnapshot:
    ready: bool
    status: str
    device_id: str | None
    playback_url: str | None
    source_protocol: str
    output_protocol: str
    connected_at: datetime | None
    reconnect_count: int
    last_error: str | None


class RelayService:
    def __init__(self, settings: RelaySettings) -> None:
        self.settings = settings
        self.client = BackendMediaClient(
            settings.backend_internal_url,
            settings.shared_token,
            settings.channel_no,
        )
        self._runner: asyncio.Task | None = None
        self._publisher_task: asyncio.Task[None] | None = None
        self._publisher_stop: threading.Event | None = None
        self._device_id: str | None = None
        self._connected_at: datetime | None = None
        self._status = "starting"
        self._reconnect_count = 0
        self._last_error: str | None = None
        self._path_ready = False
        self._media_server = httpx.AsyncClient(
            base_url=settings.media_server_api_url,
            timeout=2.0,
            trust_env=False,
        )

    async def start(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run(), name="media-relay")

    async def close(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
        await self._stop_publisher()
        await self.client.close()
        await self._media_server.aclose()

    def snapshot(self) -> RelaySnapshot:
        ready = bool(
            self._status == "connected"
            and self._path_ready
            and self._publisher_task is not None
            and not self._publisher_task.done()
        )
        return RelaySnapshot(
            ready=ready,
            status=self._status,
            device_id=self._device_id,
            playback_url=self.settings.public_read_url if ready else None,
            source_protocol="http_flv",
            output_protocol="rtsp",
            connected_at=self._connected_at,
            reconnect_count=self._reconnect_count,
            last_error=self._last_error,
        )

    async def _run(self) -> None:
        while True:
            try:
                self._status = "connecting"
                device = await self.client.select_device()
                source = await self.client.get_http_flv(device)
                self._device_id = source.device_id
                self._publisher_stop = threading.Event()
                self._publisher_task = asyncio.create_task(
                    asyncio.to_thread(
                        self._remux,
                        source.playback_url,
                        self._publisher_stop,
                    ),
                    name="media-remux",
                )
                await self._wait_until_published()
                self._status = "connected"
                self._path_ready = True
                self._connected_at = datetime.now(timezone.utc)
                self._last_error = None
                await self._monitor_publisher()
            except asyncio.CancelledError:
                await self._stop_publisher()
                raise
            except RelayMediaError as exc:
                self._status = "reconnecting"
                self._path_ready = False
                self._connected_at = None
                self._reconnect_count += 1
                self._last_error = str(exc)
                await self._stop_publisher()
                await asyncio.sleep(self.settings.reconnect_seconds)
            except Exception:
                # Keep the long-lived reconnect loop alive even if a media
                # library raises an unexpected exception. Do not retain the
                # exception text because it can contain the temporary source
                # URL and its query credentials.
                self._status = "reconnecting"
                self._path_ready = False
                self._connected_at = None
                self._reconnect_count += 1
                self._last_error = "Media relay encountered an internal failure"
                await self._stop_publisher()
                await asyncio.sleep(self.settings.reconnect_seconds)

    async def _wait_until_published(self) -> None:
        """Require a ready MediaMTX path; process survival alone is insufficient."""

        for _ in range(30):
            if self._publisher_task is None or self._publisher_task.done():
                raise RelayMediaError("Media publisher exited during startup")
            try:
                response = await self._media_server.get("/v3/paths/get/careshield")
                if response.status_code == 200 and response.json().get("ready") is True:
                    return
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(0.5)
        raise RelayMediaError("Media publisher did not expose a readable stream")

    async def _monitor_publisher(self) -> None:
        """Reconnect expired sources even when a media library remains blocked."""

        unavailable_checks = 0
        while True:
            task = self._publisher_task
            if task is None:
                raise RelayMediaError("Media publisher stopped")
            if task.done():
                await task
                raise RelayMediaError("Media publisher stopped")
            try:
                response = await self._media_server.get("/v3/paths/get/careshield")
                payload = response.json() if response.status_code == 200 else {}
                path_ready = payload.get("ready") is True
            except (httpx.HTTPError, ValueError):
                path_ready = False
            self._path_ready = path_ready
            unavailable_checks = 0 if path_ready else unavailable_checks + 1
            if unavailable_checks >= 5:
                raise RelayMediaError("Published media path became unavailable")
            await asyncio.sleep(1.0)

    async def _stop_publisher(self) -> None:
        task = self._publisher_task
        stop = self._publisher_stop
        self._publisher_task = None
        self._publisher_stop = None
        self._path_ready = False
        if stop is not None:
            stop.set()
        if task is None:
            return
        if task.done():
            self._consume_publisher_result(task)
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=20.0)
        except asyncio.TimeoutError:
            # PyAV network reads have their own 15-second timeout. The thread
            # will close naturally without spawning a second publisher.
            pass
        except RelayMediaError:
            # The publisher commonly reports its media failure while this
            # cleanup coroutine is waiting. That failure already caused the
            # reconnect and must not terminate the long-lived runner.
            pass
        except Exception:
            # Never retain/log the raw exception because FFmpeg may embed the
            # temporary playback URL in it.
            pass

    @staticmethod
    def _consume_publisher_result(task: asyncio.Task[None]) -> None:
        """Retrieve a completed task exception without re-raising or leaking it."""

        try:
            task.result()
        except (asyncio.CancelledError, RelayMediaError):
            pass
        except Exception:
            pass

    def _remux(self, source_url: str, stop: threading.Event) -> None:
        """Remux EZVIZ HEVC/AAC into RTSP with an explicit Annex-B filter.

        EZVIZ HTTP-FLV carries HEVC NAL units with length prefixes. Forwarding
        those PyAV packets directly to the RTSP muxer corrupts reference frames.
        PyAV 18 can read EZVIZ's enhanced HEVC-FLV codec tag, while the Debian
        FFmpeg 7 CLI cannot. Its FFmpeg bitstream-filter binding performs the
        required conversion without decoding, so the shared relay stays light.
        """

        source: av.InputContainer | None = None
        output: av.OutputContainer | None = None
        try:
            source = av.open(
                source_url,
                options={"rw_timeout": "15000000"},
            )
            video = next(stream for stream in source.streams if stream.type == "video")
            audio = next(
                (stream for stream in source.streams if stream.type == "audio"),
                None,
            )
            output = av.open(
                self.settings.publish_url,
                mode="w",
                format="rtsp",
                options={"rtsp_transport": "tcp"},
            )
            out_video = output.add_stream_from_template(video)
            out_audio = output.add_stream_from_template(audio) if audio else None
            annex_b = self._create_video_filter(video, out_video)

            streams = (video, audio) if audio is not None else (video,)
            for packet in source.demux(streams):
                if stop.is_set():
                    return
                if packet.dts is None:
                    continue
                if packet.stream == video:
                    for filtered in annex_b.filter(packet):
                        filtered.stream = out_video
                        output.mux(filtered)
                elif out_audio is not None:
                    packet.stream = out_audio
                    output.mux(packet)
        except (av.FFmpegError, OSError, StopIteration) as exc:
            raise RelayMediaError("Media publisher failed") from exc
        finally:
            if output is not None:
                try:
                    output.close()
                except av.FFmpegError:
                    pass
            if source is not None:
                try:
                    source.close()
                except av.FFmpegError:
                    pass

    @staticmethod
    def _create_video_filter(
        video: av.video.stream.VideoStream,
        out_video: av.video.stream.VideoStream,
    ) -> av.bitstream.BitStreamFilterContext:
        return av.bitstream.BitStreamFilterContext(
            "hevc_mp4toannexb",
            video,
            out_video,
        )
