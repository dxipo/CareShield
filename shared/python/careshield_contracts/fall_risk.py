"""Stable contracts for asynchronous fall-risk feature extraction jobs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssessmentStatus(str, Enum):
    QUEUED = "queued"
    CAPTURING = "capturing"
    PROCESSING_GAIT = "processing_gait"
    PROCESSING_GVHMR = "processing_gvhmr"
    PROCESSING_RISK = "processing_risk"
    QUALITY_REVIEW = "quality_review"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    READY = "ready"
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FallRiskAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_name: str | None = Field(default=None, min_length=1, max_length=80)
    sex: Literal["male", "female"] | None = None
    age: int | None = Field(default=None, ge=1, le=120)
    height_cm: float = Field(ge=80.0, le=230.0)
    capture_duration_seconds: int = Field(default=15, ge=8, le=60)
    device_id: str | None = Field(default=None, max_length=256)


class FallRiskVideoAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_name: str | None = Field(default=None, min_length=1, max_length=80)
    sex: Literal["male", "female"] | None = None
    age: int | None = Field(default=None, ge=1, le=120)
    height_cm: float = Field(ge=80.0, le=230.0)
    capture_duration_seconds: int = Field(ge=8, le=60)
    source_filename: str = Field(min_length=1, max_length=255)


class PipelineState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PipelineStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str | None = Field(default=None, max_length=500)


class GaitParameterValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    category: Literal["temporal", "spatial", "variability", "posture", "stability"]
    value: float | None = None
    unit: str = Field(max_length=32)
    available: bool
    unavailable_reason: str | None = Field(default=None, max_length=300)


class AssessmentQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool = False
    video_duration_seconds: float | None = Field(default=None, ge=0.0)
    original_video_duration_seconds: float | None = Field(default=None, ge=0.0)
    selected_start_seconds: float | None = Field(default=None, ge=0.0)
    selected_end_seconds: float | None = Field(default=None, ge=0.0)
    discarded_duration_seconds: float | None = Field(default=None, ge=0.0)
    source_fps: float | None = Field(default=None, ge=0.0)
    full_body_visible_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    pose_valid_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    interpolated_frame_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    maximum_missing_gap_frames: int | None = Field(default=None, ge=0)
    maximum_missing_gap_seconds: float | None = Field(default=None, ge=0.0)
    heel_strike_count: int | None = Field(default=None, ge=0)
    toe_off_count: int | None = Field(default=None, ge=0)
    complete_step_count: int | None = Field(default=None, ge=0)
    reasons: list[str] = Field(default_factory=list)


class AssessmentArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=128)
    kind: Literal[
        "source_video",
        "gait_overlay",
        "gvhmr_incamera",
        "gvhmr_global",
        "world_skeleton",
    ]
    label: str = Field(min_length=1, max_length=120)
    media_type: str = Field(min_length=1, max_length=120)
    available: bool = True


class FallRiskModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    display_name: str
    status: str
    architecture: str
    training_scope: str
    checkpoint_epoch: int
    web_interface_compatible: bool
    clinical_risk_calibrated: bool = False


class FallRiskConceptResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predicted_level: Literal["normal", "mild", "moderate", "marked", "abnormal"]
    predicted_level_id: int = Field(ge=0, le=3)
    probabilities: dict[str, float]
    top1_probability: float = Field(ge=0.0, le=1.0)
    second_best_probability: float = Field(ge=0.0, le=1.0)
    margin: float = Field(ge=0.0, le=1.0)

    @field_validator("probabilities")
    @classmethod
    def probabilities_are_bounded(cls, value: dict[str, float]) -> dict[str, float]:
        if not value or any(item < 0.0 or item > 1.0 for item in value.values()):
            raise ValueError("concept probabilities must be within [0,1]")
        return value


class FallRiskModelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: FallRiskModelInfo
    metadata: dict[str, object]
    healthy_distance: float = Field(ge=0.0, le=2.0)
    risk_level: Literal["low", "medium", "high"] | None = None
    concepts: dict[str, FallRiskConceptResult]
    explanation: str


class FallRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: UUID
    status: AssessmentStatus
    stage: str = Field(min_length=1, max_length=120)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    device_id: str | None = Field(default=None, max_length=256)
    input_source: Literal["camera", "uploaded_video"] = "camera"
    source_filename: str | None = Field(default=None, max_length=255)
    subject_name: str | None = Field(default=None, max_length=80)
    sex: Literal["male", "female"] | None = None
    age: int | None = Field(default=None, ge=1, le=120)
    height_cm: float = Field(ge=80.0, le=230.0)
    capture_duration_seconds: int = Field(ge=8, le=60)
    created_at: datetime
    started_at: datetime | None = None
    capture_started_at: datetime | None = None
    capture_completed_at: datetime | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    gait_pipeline: PipelineState
    gvhmr_pipeline: PipelineState
    risk_pipeline: PipelineState = Field(
        default_factory=lambda: PipelineState(status=PipelineStatus.NOT_CONFIGURED)
    )
    quality: AssessmentQuality = Field(default_factory=AssessmentQuality)
    gait_parameters: list[GaitParameterValue] = Field(default_factory=list)
    artifacts: list[AssessmentArtifact] = Field(default_factory=list)
    risk_model_status: Literal[
        "not_installed", "not_configured", "waiting", "running", "completed", "failed", "skipped"
    ] = "not_installed"
    risk_result: FallRiskModelResult | None = None
    error: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def skipped_pipeline_is_not_left_waiting(self) -> "FallRiskAssessment":
        # Backward-compatible normalization for manifests created before the
        # explicit skipped model state was added.
        if (
            self.risk_pipeline.status is PipelineStatus.SKIPPED
            and self.risk_model_status == "waiting"
        ):
            self.risk_model_status = "skipped"
        return self

    @field_validator(
        "created_at",
        "started_at",
        "capture_started_at",
        "capture_completed_at",
        "processing_started_at",
        "completed_at",
    )
    @classmethod
    def timestamps_must_include_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value


class FallRiskWorkerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["fall-risk-worker"] = "fall-risk-worker"
    status: Literal["ok"] = "ok"
    ready: bool
    active_assessment_id: UUID | None = None
    gait_pipeline: PipelineState
    gvhmr_pipeline: PipelineState
    risk_pipeline: PipelineState = Field(
        default_factory=lambda: PipelineState(status=PipelineStatus.NOT_CONFIGURED)
    )
    missing_requirements: list[str] = Field(default_factory=list)
