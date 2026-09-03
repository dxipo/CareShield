from typing import Literal

from pydantic import BaseModel


class VoiceBroadcastCapability(BaseModel):
    provider: Literal["ezviz"] = "ezviz"
    supported: bool
    support_talk: int | None = None
    support_alarm_voice: bool | None = None


class VoiceBroadcastResult(BaseModel):
    provider: Literal["ezviz"] = "ezviz"
    status: Literal["accepted"] = "accepted"
    channel_no: int
