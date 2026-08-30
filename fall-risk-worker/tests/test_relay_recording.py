import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.adapters.relay_recording import RelayRecordingClient


def test_timestamped_clip_uses_trigger_time_and_mp4(tmp_path) -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(dict(request.url.params))
        return httpx.Response(
            200,
            content=b"mp4-data",
            headers={"content-type": "video/mp4"},
        )

    client = RelayRecordingClient(
        "http://media-server:9996",
        finalize_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    triggered_at = datetime.now(timezone.utc) - timedelta(seconds=20)
    output = tmp_path / "source.mp4"

    async def fake_normalize(buffered_input, normalized_output, **_kwargs) -> None:
        normalized_output.write_bytes(buffered_input.read_bytes())

    client._normalize_capture = fake_normalize

    asyncio.run(
        client.capture(output, triggered_at=triggered_at, duration_seconds=15)
    )
    asyncio.run(client.close())

    assert output.read_bytes() == b"mp4-data"
    assert observed["path"] == "careshield"
    assert observed["start"] == (triggered_at - timedelta(seconds=8)).isoformat()
    assert observed["duration"] == "23.0"
    assert observed["format"] == "mp4"


def test_capture_normalization_decodes_preroll_and_encodes_h264(tmp_path) -> None:
    client = RelayRecordingClient(
        "http://media-server:9996",
        finalize_seconds=0,
        pre_roll_seconds=8,
    )

    command = client._normalization_command(
        tmp_path / "buffered.mp4",
        tmp_path / "source.mp4",
        duration_seconds=15,
    )

    assert command[command.index("-ss") + 1] == "8"
    assert command[command.index("-t") + 1] == "15"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    asyncio.run(client.close())
