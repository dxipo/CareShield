from __future__ import annotations

import asyncio
from pathlib import Path


class CaptureError(RuntimeError):
    """Safe capture error without exposing the temporary playback URL."""


async def capture_video(playback_url: str, output: Path, duration_seconds: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    input_options = []
    timeout_options = ["-rw_timeout", "15000000"]
    if playback_url.startswith("rtsp://"):
        # Assessment capture favors complete HEVC reference frames. `nobuffer`
        # can discard the first reference pictures when attaching mid-GOP and
        # leave a short capture with no encodable frames.
        input_options = ["-rtsp_transport", "tcp"]
        timeout_options = ["-timeout", "15000000"]
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        *timeout_options,
        *input_options,
        "-i",
        playback_url,
        "-t",
        str(duration_seconds),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(output),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return_code = await process.wait()
    if return_code != 0 or not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise CaptureError("Camera assessment clip could not be captured")
