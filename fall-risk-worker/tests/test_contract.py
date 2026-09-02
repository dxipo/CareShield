from datetime import datetime, timezone
from uuid import uuid4

import pytest
from careshield_contracts import (
    AssessmentStatus,
    FallRiskAssessment,
    PipelineState,
    PipelineStatus,
    FallRiskVideoAssessmentCreate,
    KinecalFallRiskResult,
)
from pydantic import ValidationError


def assessment():
    return FallRiskAssessment(
        assessment_id=uuid4(),
        status=AssessmentStatus.QUEUED,
        stage="waiting",
        height_cm=170,
        capture_duration_seconds=15,
        created_at=datetime.now(timezone.utc),
        gait_pipeline=PipelineState(status=PipelineStatus.WAITING),
        gvhmr_pipeline=PipelineState(status=PipelineStatus.NOT_CONFIGURED),
    )


def test_risk_result_is_explicitly_unavailable() -> None:
    value = assessment()
    assert value.risk_model_status == "not_installed"
    assert value.risk_result is None


def test_height_and_timezone_are_validated() -> None:
    payload = assessment().model_dump()
    payload["height_cm"] = 40
    with pytest.raises(ValidationError):
        FallRiskAssessment.model_validate(payload)
    payload = assessment().model_dump()
    payload["created_at"] = datetime.now()
    with pytest.raises(ValidationError):
        FallRiskAssessment.model_validate(payload)


def test_uploaded_video_contract_is_explicit_and_bounded() -> None:
    request = FallRiskVideoAssessmentCreate(
        subject_name="测试受试者",
        sex="female",
        age=72,
        height_cm=168,
        capture_duration_seconds=39,
        source_filename="walking.mp4",
    )
    assert request.source_filename == "walking.mp4"
    assert request.subject_name == "测试受试者"
    assert request.age == 72
    payload = assessment().model_copy(
        update={"input_source": "uploaded_video", "source_filename": "walking.mp4"}
    )
    assert payload.input_source == "uploaded_video"

    with pytest.raises(ValidationError):
        FallRiskVideoAssessmentCreate(
            subject_name="测试受试者",
            sex="female",
            age=72,
            height_cm=168,
            capture_duration_seconds=61,
            source_filename="walking.mp4",
        )


def test_subject_demographics_are_bounded() -> None:
    with pytest.raises(ValidationError):
        FallRiskVideoAssessmentCreate(
            subject_name="测试受试者",
            sex="female",
            age=121,
            height_cm=168,
            capture_duration_seconds=15,
            source_filename="walking.mp4",
        )


def test_quality_gate_can_explicitly_skip_the_risk_model() -> None:
    value = assessment().model_copy(update={"risk_model_status": "skipped"})
    assert value.risk_model_status == "skipped"


def test_kinecal_result_requires_bounded_three_class_probabilities() -> None:
    payload = {
        "model": {
            "model_id": "kinecal-stgcnpp-walk",
            "display_name": "KINECAL risk",
            "architecture": "stgcnpp_action_adapter",
            "version": "walk-v2-fold2",
            "checkpoint_sha256": "e" * 64,
            "training_domain": "KINECAL",
            "clinical_risk_calibrated": False,
        },
        "risk_level": "medium",
        "predicted_class": 1,
        "predicted_group": "FHs",
        "class_probabilities": {"low": 0.2, "medium": 0.7, "high": 0.1},
        "raw_class_probabilities": {"low": 0.3, "medium": 0.6, "high": 0.1},
        "confidence": 0.7,
        "action_type": "3m-walk-Front-View",
        "source_frames": 300,
        "source_fps": 30,
        "source_duration_seconds": 10,
        "clip_frames": 120,
        "input_adapter": "gvhmr_world21_to_kinecal_h36m17_v1",
        "input_quality": "usable",
        "limitations": [],
        "metadata": {},
    }
    result = KinecalFallRiskResult.model_validate(payload)
    assert result.predicted_group == "FHs"

    payload["class_probabilities"] = {"low": 0.2, "medium": 0.2, "high": 0.2}
    with pytest.raises(ValidationError):
        KinecalFallRiskResult.model_validate(payload)
