from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

import av
import httpx
import numpy as np

from app.core.config import FraudWorkerSettings


class AudioReaderError(RuntimeError):
    """A redacted media error that never embeds a stream address."""


@dataclass(frozen=True, slots=True)
class AudioChunk:
    pcm_s16le: bytes
    timestamp: datetime
    sample_rate: int


class AudioReader:
    """Read only the audio track from CareShield's authenticated shared relay."""

    def __init__(self, settings: FraudWorkerSettings) -> None:
        self.settings = settings
        self.device_id: str | None = None
        self._client = httpx.Client(
            base_url=settings.media_relay_internal_url,
            headers={"Authorization": f"Bearer {settings.shared_token}"},
            timeout=settings.request_timeout_seconds,
            trust_env=False,
        )

    def chunks(self) -> Iterator[AudioChunk]:
        playback_url = self._relay_url()
        container: av.InputContainer | None = None
        try:
            container = av.open(
                playback_url,
                options={"rtsp_transport": "tcp", "rw_timeout": "15000000"},
            )
            audio = next(
                (stream for stream in container.streams if stream.type == "audio"),
                None,
            )
            if audio is None:
                raise AudioReaderError("Shared camera stream has no audio track")
            resampler = av.audio.resampler.AudioResampler(
                format="s16",
                layout="mono",
                rate=self.settings.audio_sample_rate,
            )
            for frame in container.decode(audio):
                for converted in resampler.resample(frame):
                    samples = converted.to_ndarray().reshape(-1).astype(
                        np.int16, copy=False
                    )
                    if samples.size:
                        yield AudioChunk(
                            pcm_s16le=samples.tobytes(),
                            timestamp=datetime.now(timezone.utc),
                            sample_rate=self.settings.audio_sample_rate,
                        )
        except AudioReaderError:
            raise
        except (av.FFmpegError, httpx.HTTPError, OSError, StopIteration) as exc:
            raise AudioReaderError("Unable to consume shared camera audio") from exc
        finally:
            if container is not None:
                try:
                    container.close()
                except av.FFmpegError:
                    pass

    def close(self) -> None:
        self._client.close()

    def _relay_url(self) -> str:
        try:
            response = self._client.get("/stream")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AudioReaderError("Shared media relay is unreachable") from exc
        url = payload.get("playback_url") if isinstance(payload, dict) else None
        if payload.get("ready") is not True or not isinstance(url, str) or not url:
            raise AudioReaderError("Shared camera stream is not ready")
        device_id = payload.get("device_id")
        self.device_id = device_id if isinstance(device_id, str) and device_id else None
        return url
