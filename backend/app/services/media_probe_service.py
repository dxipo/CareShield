import asyncio
import json
from fractions import Fraction
from typing import Any

from app.schemas.stream import AudioMediaInfo, MediaInfo, VideoMediaInfo
from app.services.stream_service import StreamService


class MediaProbeError(Exception):
    """Safe ffprobe failure that never includes a playback address."""


class MediaProbeService:
    def __init__(
        self,
        stream_service: StreamService,
        *,
        executable: str = "ffprobe",
        timeout_seconds: float = 25.0,
    ) -> None:
        self.stream_service = stream_service
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    async def probe(self, device_serial: str, *, channel_no: int = 1) -> MediaInfo:
        playback = await self.stream_service.get_live_stream(
            device_serial,
            channel_no=channel_no,
        )
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-v",
                "error",
                "-rw_timeout",
                "15000000",
                "-show_entries",
                (
                    "stream=codec_type,codec_name,codec_long_name,profile,width,height,"
                    "pix_fmt,r_frame_rate,avg_frame_rate,bit_rate,level,sample_rate,"
                    "channels,channel_layout"
                ),
                "-of",
                "json",
                playback.playback_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise MediaProbeError("ffprobe is not available") from exc

        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise MediaProbeError("Media probe timed out") from exc

        if process.returncode != 0:
            raise MediaProbeError("Unable to inspect the live stream")

        try:
            payload = json.loads(stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaProbeError("ffprobe returned invalid metadata") from exc

        return self.parse_payload(
            payload,
            device_id=playback.device_id,
            channel_no=channel_no,
        )

    @classmethod
    def parse_payload(
        cls,
        payload: Any,
        *,
        device_id: str,
        channel_no: int,
    ) -> MediaInfo:
        streams = payload.get("streams") if isinstance(payload, dict) else None
        if not isinstance(streams, list):
            raise MediaProbeError("ffprobe response has no stream metadata")

        video_raw = next(
            (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
            None,
        )
        audio_raw = next(
            (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"),
            None,
        )

        video = None
        if video_raw is not None:
            average_rate = cls._text(video_raw.get("avg_frame_rate"))
            frame_rate = cls._text(video_raw.get("r_frame_rate"))
            video = VideoMediaInfo(
                codec_name=cls._text(video_raw.get("codec_name")),
                codec_long_name=cls._text(video_raw.get("codec_long_name")),
                width=cls._integer(video_raw.get("width")),
                height=cls._integer(video_raw.get("height")),
                pixel_format=cls._text(video_raw.get("pix_fmt")),
                fps=cls._rate(average_rate) or cls._rate(frame_rate),
                frame_rate=frame_rate,
                average_frame_rate=average_rate,
                bitrate=cls._integer(video_raw.get("bit_rate")),
                profile=cls._text(video_raw.get("profile")),
                level=cls._integer(video_raw.get("level")),
            )

        audio = AudioMediaInfo(available=audio_raw is not None)
        if audio_raw is not None:
            audio = AudioMediaInfo(
                available=True,
                codec_name=cls._text(audio_raw.get("codec_name")),
                sample_rate=cls._integer(audio_raw.get("sample_rate")),
                channels=cls._integer(audio_raw.get("channels")),
                channel_layout=cls._text(audio_raw.get("channel_layout")),
                bitrate=cls._integer(audio_raw.get("bit_rate")),
            )

        return MediaInfo(
            device_id=device_id,
            channel_no=channel_no,
            video=video,
            audio=audio,
        )

    @staticmethod
    def _text(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _rate(value: str | None) -> float | None:
        if not value or value in {"0/0", "N/A"}:
            return None
        try:
            return round(float(Fraction(value)), 3)
        except (ValueError, ZeroDivisionError):
            return None
