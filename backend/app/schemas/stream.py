from typing import Literal

from pydantic import BaseModel


class StreamPlayback(BaseModel):
    device_id: str
    channel_no: int
    protocol: Literal["hls"] = "hls"
    playback_url: str
    expires_at: str | None = None
    quality: Literal["high", "fluent"]
    requested_video_codec: Literal["h265"] = "h265"
    container: Literal["mpeg-ts"] = "mpeg-ts"
    muted: bool = False


class BrowserPlaybackSession(BaseModel):
    """Ephemeral credentials required by the official EZOPEN Web SDK.

    This response must never be cached, persisted, logged, or reused as a
    general-purpose CareShield API response.
    """

    device_id: str
    channel_no: int
    protocol: Literal["ezopen"] = "ezopen"
    playback_url: str
    access_token: str
    decoder: Literal["v3"] = "v3"
    quality: Literal["performance"] = "performance"


class VideoMediaInfo(BaseModel):
    codec_name: str | None = None
    codec_long_name: str | None = None
    width: int | None = None
    height: int | None = None
    pixel_format: str | None = None
    fps: float | None = None
    frame_rate: str | None = None
    average_frame_rate: str | None = None
    bitrate: int | None = None
    profile: str | None = None
    level: int | None = None


class AudioMediaInfo(BaseModel):
    available: bool
    codec_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    bitrate: int | None = None


class MediaInfo(BaseModel):
    device_id: str
    channel_no: int
    probe_success: bool
    camera_content_verified: bool
    video: VideoMediaInfo | None = None
    audio: AudioMediaInfo
