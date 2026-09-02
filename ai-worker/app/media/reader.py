from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

from app.media.backend_client import BackendMediaClient, MediaBackendError


logger = logging.getLogger(__name__)


class MediaReaderError(RuntimeError):
    """A redacted decoder error that never contains a playback URL."""


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    image: Any
    captured_at: datetime
    media_seconds: float
    arrival_monotonic_seconds: float
    source_width: int
    source_height: int
    source_fps: float | None


class _PyAvSession:
    def __init__(self, playback_url: str) -> None:
        try:
            import av

            options = {"rw_timeout": "10000000"}
            if playback_url.startswith("rtsp://"):
                options.update(
                    {
                        "rtsp_transport": "tcp",
                        "fflags": "discardcorrupt",
                    }
                )
            self._container = av.open(
                playback_url,
                mode="r",
                timeout=(10.0, 10.0),
                options=options,
            )
            video_streams = self._container.streams.video
            if not video_streams:
                raise MediaReaderError("Temporary stream has no video track")
            self._stream = video_streams[0]
            self._stream.thread_type = "AUTO"
            self._frames = self._container.decode(self._stream)
            self._synchronized = False
        except MediaReaderError:
            raise
        except Exception as exc:
            raise MediaReaderError("Unable to open temporary camera stream") from exc

    def next_frame(self) -> DecodedFrame | None:
        while True:
            try:
                frame = next(self._frames)
            except StopIteration:
                return None
            except Exception as exc:
                raise MediaReaderError("Camera stream decoding failed") from exc

            # Do not expose pictures decoded from an incomplete HEVC reference
            # chain. After a corrupt frame, wait for the next IDR before
            # resuming inference and the operator preview.
            if getattr(frame, "is_corrupt", False):
                self._synchronized = False
                continue
            if not self._synchronized:
                if not getattr(frame, "key_frame", False):
                    continue
                self._synchronized = True
            break

        try:
            rate = float(self._stream.average_rate) if self._stream.average_rate else None
            arrival_monotonic_seconds = time.monotonic()
            media_seconds = (
                float(frame.time)
                if frame.time is not None
                else arrival_monotonic_seconds
            )
            return DecodedFrame(
                image=frame.to_ndarray(format="bgr24"),
                captured_at=datetime.now(timezone.utc),
                media_seconds=media_seconds,
                arrival_monotonic_seconds=arrival_monotonic_seconds,
                source_width=frame.width,
                source_height=frame.height,
                source_fps=rate,
            )
        except Exception as exc:
            raise MediaReaderError("Decoded camera frame conversion failed") from exc

    def close(self) -> None:
        self._container.close()


class MediaReader:
    """Refreshable H.265 reader with URL-safe reconnect logging.

    The browser uses EZOPEN while the Backend issues HTTP-FLV to this reader,
    keeping camera credentials out of the Worker and reducing inference delay.
    """

    def __init__(
        self,
        client: BackendMediaClient,
        *,
        reconnect_seconds: float = 3.0,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._client = client
        self._reconnect_seconds = reconnect_seconds
        self._status_callback = status_callback or (lambda _: None)
        self.reconnect_count = 0
        self.last_disconnect_reason: str | None = None
        self.last_session_frames = 0
        self.last_session_seconds: float | None = None

    async def frames(self, device_serial: str) -> AsyncIterator[DecodedFrame]:
        while True:
            session: _PyAvSession | None = None
            session_frames = 0
            session_started = time.monotonic()
            try:
                self._status_callback("connecting")
                temporary_stream = await self._client.get_stream(device_serial)
                session = await asyncio.to_thread(
                    _PyAvSession,
                    temporary_stream.playback_url,
                )
                self._status_callback("connected")
                self.last_disconnect_reason = None
                while True:
                    frame = await asyncio.to_thread(session.next_frame)
                    if frame is None:
                        raise MediaReaderError("Camera stream ended")
                    session_frames += 1
                    yield frame
            except asyncio.CancelledError:
                raise
            except (MediaBackendError, MediaReaderError) as exc:
                self.reconnect_count += 1
                self.last_disconnect_reason = str(exc)
                self.last_session_frames = session_frames
                self.last_session_seconds = time.monotonic() - session_started
                self._status_callback("reconnecting")
                logger.warning(
                    "Camera media input unavailable (%s); retrying with a fresh address",
                    self.last_disconnect_reason,
                )
                await asyncio.sleep(self._reconnect_seconds)
            finally:
                if session is not None:
                    try:
                        await asyncio.to_thread(session.close)
                    except Exception:
                        logger.warning("Camera decoder cleanup failed")
