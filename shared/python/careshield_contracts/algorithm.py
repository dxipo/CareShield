"""Canonical Python contract for CareShield realtime algorithm results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class AlgorithmTask(str, Enum):
    FALL_DETECTION = "fall_detection"
    FALL_RISK = "fall_risk"
    FRAUD_DETECTION = "fraud_detection"
    PIPELINE_TEST = "pipeline_test"


class RiskLevel(str, Enum):
    NORMAL = "normal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlgorithmResult(BaseModel):
    """Stable, model-framework-independent algorithm result."""

    model_config = ConfigDict(extra="forbid")

    result_id: UUID
    task: AlgorithmTask
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    device_id: str | None = Field(default=None, max_length=256)
    source_timestamp: datetime | None = None
    result_timestamp: datetime
    label: str = Field(min_length=1, max_length=128)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    level: RiskLevel | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    simulated: bool

    @field_validator("source_timestamp", "result_timestamp")
    @classmethod
    def timestamps_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def pipeline_test_must_be_simulated(self) -> "AlgorithmResult":
        if self.task == AlgorithmTask.PIPELINE_TEST and not self.simulated:
            raise ValueError("pipeline_test results must set simulated=true")
        return self


class AlgorithmCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fall_detection: Literal["not_installed"] = "not_installed"
    fall_risk: Literal["not_installed"] = "not_installed"
    fraud_detection: Literal["not_installed"] = "not_installed"


class WorkerHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=128)
    online: bool
    timestamp: datetime
    version: str = Field(min_length=1, max_length=64)
    capabilities: AlgorithmCapabilities

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value


class RealtimeMessageType(str, Enum):
    ALGORITHM_RESULT = "algorithm_result"
    WORKER_STATUS = "worker_status"


class RealtimeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: RealtimeMessageType
    timestamp: datetime
    data: dict[str, JsonValue]

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value
