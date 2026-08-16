#!/usr/bin/env python3
"""Probe a live EZVIZ stream through CareShield without printing its URL."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def get_json(url: str, *, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def choose_device(devices: Any) -> dict[str, Any]:
    if not isinstance(devices, list):
        raise RuntimeError("CareShield returned an invalid device list")
    online = [item for item in devices if isinstance(item, dict) and item.get("online") is True]
    h6c = next(
        (
            item
            for item in online
            if "h6c" in f"{item.get('model', '')} {item.get('name', '')}".lower()
        ),
        None,
    )
    device = h6c or (online[0] if online else None)
    if device is None:
        raise RuntimeError("No online EZVIZ camera is available")
    return device


def safe_metadata(payload: Any) -> dict[str, Any]:
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    video = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    audio = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"),
        None,
    )
    video_fields = (
        "codec_name",
        "codec_long_name",
        "profile",
        "width",
        "height",
        "pix_fmt",
        "r_frame_rate",
        "avg_frame_rate",
        "bit_rate",
        "level",
    )
    audio_fields = (
        "codec_name",
        "sample_rate",
        "channels",
        "channel_layout",
        "bit_rate",
    )
    return {
        "video": {key: video.get(key) for key in video_fields} if video else None,
        "audio": {
            "available": audio is not None,
            **({key: audio.get(key) for key in audio_fields} if audio else {}),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--channel-no", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    base_url = args.api_base_url.rstrip("/")

    try:
        device = choose_device(get_json(f"{base_url}/api/devices", timeout=args.timeout))
        serial = device.get("device_serial")
        if not isinstance(serial, str) or not serial:
            raise RuntimeError("Selected device has no serial number")
        query = urllib.parse.urlencode(
            {"channel_no": args.channel_no, "quality": "high"}
        )
        playback = get_json(
            f"{base_url}/api/devices/{urllib.parse.quote(serial, safe='')}/stream?{query}",
            timeout=args.timeout,
        )
        playback_url = playback.get("playback_url") if isinstance(playback, dict) else None
        if not isinstance(playback_url, str) or not playback_url:
            raise RuntimeError("CareShield returned no playback address")

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-rw_timeout",
                str(int(args.timeout * 1_000_000)),
                "-show_entries",
                (
                    "stream=codec_type,codec_name,codec_long_name,profile,width,height,"
                    "pix_fmt,r_frame_rate,avg_frame_rate,bit_rate,level,sample_rate,"
                    "channels,channel_layout"
                ),
                "-of",
                "json",
                playback_url,
            ],
            capture_output=True,
            check=False,
            timeout=args.timeout + 5,
        )
        if result.returncode != 0:
            raise RuntimeError("ffprobe could not read the live stream")
        print(json.dumps(safe_metadata(json.loads(result.stdout)), indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        print(f"Probe failed: CareShield API returned HTTP {exc.code}", file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("Probe failed: CareShield API is unavailable", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"Probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
