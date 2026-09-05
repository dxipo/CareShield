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


class GaitAnalysisState(BaseModel):
    """Versioned provenance for legacy/GaitKit rollout and safe fallback."""

    model_config = ConfigDict(extra="forbid")

    requested_mode: Literal["legacy", "gaitkit_shadow", "gaitkit_primary"] = "legacy"
    primary_source: Literal["visionmd_camera", "gaitkit_world"] = "visionmd_camera"
    primary_algorithm_id: str = "visionmd-metrabs-camera-gait-parameters"
    primary_algorithm_version: str = "legacy-v1"
    gaitkit_status: Literal[
        "not_configured", "waiting", "running", "completed", "failed", "skipped"
    ] = "not_configured"
    shadow_algorithm_id: str | None = None
    shadow_algorithm_version: str | None = None
    metric_definition_version: str | None = None
    analysis_fps: float | None = Field(default=None, gt=0.0)
    fallback_used: bool = False
    message: str | None = Field(default=None, max_length=300)


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


class KinecalRiskModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    architecture: Literal["stgcnpp_action_adapter"] = "stgcnpp_action_adapter"
    version: str = Field(min_length=1, max_length=80)
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_domain: str = Field(min_length=1, max_length=300)
    clinical_risk_calibrated: bool = False


class KinecalFallRiskResult(BaseModel):
    """Three-class KINECAL cohort result, kept separate from MotionCLIP."""

    model_config = ConfigDict(extra="forbid")

    model: KinecalRiskModelInfo
    risk_level: Literal["low", "medium", "high"]
    predicted_class: Literal[0, 1, 2]
    predicted_group: Literal["NF", "FHs", "FHm"]
    class_probabilities: dict[Literal["low", "medium", "high"], float]
    raw_class_probabilities: dict[Literal["low", "medium", "high"], float]
    confidence: float = Field(ge=0.0, le=1.0)
    action_type: Literal["3m-walk-Front-View"]
    source_frames: int = Field(ge=1)
    source_fps: float = Field(gt=0.0)
    source_duration_seconds: float = Field(gt=0.0)
    clip_frames: Literal[120] = 120
    input_adapter: str = Field(min_length=1, max_length=120)
    input_quality: Literal["usable", "review"]
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("class_probabilities", "raw_class_probabilities")
    @classmethod
    def class_probabilities_are_valid(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        if set(value) != {"low", "medium", "high"}:
            raise ValueError("all three risk probabilities are required")
        if any(item < 0.0 or item > 1.0 for item in value.values()):
            raise ValueError("risk probabilities must be within [0,1]")
        if abs(sum(value.values()) - 1.0) > 1e-4:
            raise ValueError("risk probabilities must sum to one")
        return value


class FallRiskScreeningResult(BaseModel):
    """User-facing binary screening derived from the preserved KINECAL result."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["normal", "at_risk", "review_required", "unavailable"]
    normal_evidence: float = Field(ge=0.0, le=1.0)
    risk_evidence: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_model_id: str = Field(min_length=1, max_length=120)
    raw_risk_level: Literal["low", "medium", "high"]
    raw_group: Literal["NF", "FHs", "FHm"]
    decision_version: Literal["kinecal-binary-gate-v1"] = "kinecal-binary-gate-v1"
    discordant: bool = False
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def evidence_sums_to_one(self) -> "FallRiskScreeningResult":
        if abs(self.normal_evidence + self.risk_evidence - 1.0) > 1e-4:
            raise ValueError("binary screening evidence must sum to one")
        return self


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
    gait_analysis: GaitAnalysisState = Field(default_factory=GaitAnalysisState)
    gait_parameters: list[GaitParameterValue] = Field(default_factory=list)
    artifacts: list[AssessmentArtifact] = Field(default_factory=list)
    risk_model_status: Literal[
        "not_installed", "not_configured", "waiting", "running", "completed", "failed", "skipped"
    ] = "not_installed"
    risk_result: FallRiskModelResult | None = None
    kinecal_pipeline: PipelineState = Field(
        default_factory=lambda: PipelineState(status=PipelineStatus.NOT_CONFIGURED)
    )
    kinecal_model_status: Literal[
        "not_installed", "not_configured", "waiting", "running", "completed", "failed", "skipped"
    ] = "not_installed"
    fall_risk_result: KinecalFallRiskResult | None = None
    screening_result: FallRiskScreeningResult | None = None
    secondary_assessment_status: Literal[
        "waiting", "not_triggered", "completed", "review_required", "unavailable"
    ] = "waiting"
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

        # Keep raw three-class and MotionCLIP outputs untouched while deriving
        # the stable user-facing screening decision. This also upgrades old
        # manifests when they are read from the assessment volume.
        if self.fall_risk_result is None:
            self.screening_result = None
            if self.risk_model_status in {"failed", "skipped", "not_configured", "not_installed"}:
                self.secondary_assessment_status = "unavailable"
            return self

        result = self.fall_risk_result
        normal_evidence = result.class_probabilities["low"]
        risk_evidence = (
            result.class_probabilities["medium"]
            + result.class_probabilities["high"]
        )
        # The KINECAL classifier is the authoritative first-stage screening
        # gate. The secondary GAITCLIP representation must not turn a usable
        # low-risk screening result into a user-facing warning.
        discordant = False
        if result.risk_level in {"medium", "high"}:
            outcome = "at_risk"
            reason = "一级筛查结果更接近存在跌倒史参考队列"
        elif result.input_quality == "review":
            outcome = "review_required"
            reason = "一级筛查分类置信度不足，需要复测或人工复核"
        else:
            outcome = "normal"
            reason = "一级筛查结果更接近无跌倒史参考队列"
        self.screening_result = FallRiskScreeningResult(
            outcome=outcome,
            normal_evidence=normal_evidence,
            risk_evidence=risk_evidence,
            confidence=result.confidence,
            source_model_id=result.model.model_id,
            raw_risk_level=result.risk_level,
            raw_group=result.predicted_group,
            discordant=discordant,
            reason=reason,
        )

        if self.risk_result is None:
            self.secondary_assessment_status = (
                "unavailable"
                if self.risk_model_status in {"failed", "skipped", "not_configured", "not_installed"}
                else "waiting"
            )
        elif outcome == "normal":
            self.secondary_assessment_status = "not_triggered"
        elif outcome == "review_required" or not self.quality.passed:
            self.secondary_assessment_status = "review_required"
        else:
            self.secondary_assessment_status = "completed"
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
    gait_parameter_mode: Literal["legacy", "gaitkit_shadow", "gaitkit_primary"] = "legacy"
    gaitkit_pipeline: PipelineState = Field(
        default_factory=lambda: PipelineState(status=PipelineStatus.NOT_CONFIGURED)
    )
    gvhmr_pipeline: PipelineState
    risk_pipeline: PipelineState = Field(
        default_factory=lambda: PipelineState(status=PipelineStatus.NOT_CONFIGURED)
    )
    kinecal_pipeline: PipelineState = Field(
        default_factory=lambda: PipelineState(status=PipelineStatus.NOT_CONFIGURED)
    )
    missing_requirements: list[str] = Field(default_factory=list)
