from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelaySettings:
    backend_internal_url: str
    shared_token: str
    channel_no: int
    publish_url: str
    public_read_url: str
    media_server_api_url: str
    reconnect_seconds: float


def load_settings() -> RelaySettings:
    return RelaySettings(
        backend_internal_url=os.getenv(
            "BACKEND_INTERNAL_URL", "http://backend:8000"
        ).strip().rstrip("/"),
        shared_token=os.getenv("AI_WORKER_SHARED_TOKEN", "").strip(),
        channel_no=int(os.getenv("MEDIA_RELAY_CHANNEL_NO", "1")),
        publish_url=os.getenv(
            "MEDIA_RELAY_PUBLISH_URL", "rtsp://media-server:8554/careshield"
        ).strip(),
        public_read_url=os.getenv(
            "MEDIA_RELAY_READ_URL", "rtsp://media-server:8554/careshield"
        ).strip(),
        media_server_api_url=os.getenv(
            "MEDIA_RELAY_MEDIA_SERVER_API_URL", "http://media-server:9997"
        ).strip().rstrip("/"),
        reconnect_seconds=float(os.getenv("MEDIA_RELAY_RECONNECT_SECONDS", "3")),
    )
