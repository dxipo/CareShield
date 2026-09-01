from __future__ import annotations

import asyncio
from pathlib import Path


class MediaIntegrityError(RuntimeError):
    """A safe capture failure that never exposes internal media locations."""


DECODE_ERROR_MARKERS = (
    "invalid undecodable nalu",
    "cu_qp_delta",
    "cabac_max_bin",
    "error while decoding",
    "corrupt decoded frame",
    "invalid data found when processing input",
)


def browser_preview_command(source: Path, output: Path) -> list[str]:
    """Build a browser-compatible H.264 MP4 while preserving the source file."""

    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(output),
    ]


async def create_browser_preview(source: Path, output: Path) -> None:
    """Create the HTML5 preview used by assessment history playback."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.tmp.mp4")
    temporary.unlink(missing_ok=True)
    process = await asyncio.create_subprocess_exec(
        *browser_preview_command(source, temporary),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return_code = await process.wait()
    if return_code != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise MediaIntegrityError("Browser-compatible assessment preview could not be created")
    temporary.replace(output)


def contains_decode_error(stderr: str) -> bool:
    normalized = stderr.lower()
    if any(marker in normalized for marker in DECODE_ERROR_MARKERS):
        return True
    # Joining an HEVC stream between keyframes can produce one missing-reference
    # warning before the next IDR. Repeated loss indicates a damaged capture.
    return normalized.count("could not find ref with poc") >= 3


async def validate_video_capture(path: Path) -> None:
    """Decode the captured video once and reject damaged codec payloads.

    FFmpeg can return success after concealing damaged HEVC frames, therefore
    the known decoder diagnostics must be checked in addition to the exit code.
    """

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    diagnostics = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0 or contains_decode_error(diagnostics):
        raise MediaIntegrityError(
            "Captured camera video failed media integrity validation"
        )
