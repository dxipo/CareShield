from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


class BufferedCaptureError(RuntimeError):
    """A safe ring-buffer capture failure without internal media addresses."""


class RelayRecordingClient:
    def __init__(
        self,
        base_url: str,
        *,
        path_name: str = "careshield",
        finalize_seconds: float = 3.0,
        pre_roll_seconds: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._path_name = path_name
        self._finalize_seconds = finalize_seconds
        self._pre_roll_seconds = pre_roll_seconds
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=90.0,
            trust_env=False,
            transport=transport,
        )

    async def capture(
        self,
        output: Path,
        *,
        triggered_at: datetime,
        duration_seconds: int,
    ) -> None:
        """Download the exact post-trigger range from the rolling recording."""

        ready_at = triggered_at + timedelta(
            seconds=duration_seconds + self._finalize_seconds
        )
        wait_seconds = (ready_at - datetime.now(timezone.utc)).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        buffered_start = triggered_at - timedelta(seconds=self._pre_roll_seconds)
        buffered_duration = duration_seconds + self._pre_roll_seconds
        try:
            response = await self._client.get(
                "/get",
                params={
                    "path": self._path_name,
                    "start": buffered_start.isoformat(),
                    "duration": buffered_duration,
                    "format": "mp4",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BufferedCaptureError(
                "Timestamped camera assessment clip could not be captured"
            ) from exc
        if not response.content or "video/mp4" not in response.headers.get(
            "content-type", ""
        ):
            raise BufferedCaptureError(
                "Timestamped camera assessment clip could not be captured"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        buffered_output = output.with_name(f"{output.stem}.buffered.mp4")
        buffered_output.write_bytes(response.content)
        try:
            await self._normalize_capture(
                buffered_output,
                output,
                duration_seconds=duration_seconds,
            )
        finally:
            buffered_output.unlink(missing_ok=True)

    async def _normalize_capture(
        self,
        buffered_input: Path,
        output: Path,
        *,
        duration_seconds: int,
    ) -> None:
        """Decode pre-roll, then encode an exact clean post-trigger clip.

        MediaMTX playback can begin between HEVC keyframes. The hidden pre-roll
        supplies the missing references; output starts at the original trigger
        and is normalized to H.264 for both research pipelines.
        """

        process = await asyncio.create_subprocess_exec(
            *self._normalization_command(
                buffered_input,
                output,
                duration_seconds=duration_seconds,
            ),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            output.unlink(missing_ok=True)
            raise BufferedCaptureError(
                "Timestamped camera assessment clip could not be normalized"
            )

    def _normalization_command(
        self,
        buffered_input: Path,
        output: Path,
        *,
        duration_seconds: int,
    ) -> list[str]:
        return [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(buffered_input),
            "-ss",
            str(self._pre_roll_seconds),
            "-t",
            str(duration_seconds),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-movflags",
            "+faststart",
            str(output),
        ]

    async def close(self) -> None:
        await self._client.aclose()
