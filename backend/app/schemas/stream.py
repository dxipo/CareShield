from typing import Literal

from pydantic import BaseModel


class StreamPlayback(BaseModel):
    device_id: str
    channel_no: int
    protocol: Literal["hls"] = "hls"
    playback_url: str
    expires_at: str | None = None
    quality: Literal["high", "fluent"]


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
    video: VideoMediaInfo | None = None
    audio: AudioMediaInfo
