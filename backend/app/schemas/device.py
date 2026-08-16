from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeviceChannel(BaseModel):
    number: int | None = None
    name: str | None = None


class DeviceSummary(BaseModel):
    id: str
    provider: Literal["ezviz"] = "ezviz"
    device_serial: str
    name: str | None = None
    model: str | None = None
    online: bool | None = None
    status: Literal["online", "offline", "unknown"]
    device_type: str | None = None
    camera_count: int | None = None
    channels: list[DeviceChannel] = Field(default_factory=list)
    updated_at: datetime | None = None


class DeviceDetail(DeviceSummary):
    local_name: str | None = None
    firmware_version: str | None = None
    network_type: str | None = None
    signal: str | None = None


class EzvizIntegrationStatus(BaseModel):
    configured: bool
    reachable: bool
    message: str | None = None
