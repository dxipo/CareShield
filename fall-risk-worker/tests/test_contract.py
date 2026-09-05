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


def test_legacy_manifest_gets_backward_compatible_gait_provenance() -> None:
    value = assessment()
    assert value.gait_analysis.requested_mode == "legacy"
    assert value.gait_analysis.primary_source == "visionmd_camera"
    assert value.gait_analysis.fallback_used is False


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


def kinecal_payload(
    risk_level: str,
    *,
    input_quality: str = "usable",
) -> dict:
    probabilities = {
        "low": {"low": 0.9, "medium": 0.08, "high": 0.02},
        "medium": {"low": 0.2, "medium": 0.7, "high": 0.1},
        "high": {"low": 0.1, "medium": 0.2, "high": 0.7},
    }[risk_level]
    class_id = {"low": 0, "medium": 1, "high": 2}[risk_level]
    return {
        "model": {
            "model_id": "kinecal-stgcnpp-walk",
            "display_name": "KINECAL risk",
            "architecture": "stgcnpp_action_adapter",
            "version": "walk-v2-fold2",
            "checkpoint_sha256": "e" * 64,
            "training_domain": "KINECAL",
            "clinical_risk_calibrated": False,
        },
        "risk_level": risk_level,
        "predicted_class": class_id,
        "predicted_group": ("NF", "FHs", "FHm")[class_id],
        "class_probabilities": probabilities,
        "raw_class_probabilities": probabilities,
        "confidence": probabilities[risk_level],
        "action_type": "3m-walk-Front-View",
        "source_frames": 300,
        "source_fps": 30,
        "source_duration_seconds": 10,
        "clip_frames": 120,
        "input_adapter": "gvhmr_world21_to_kinecal_h36m17_v1",
        "input_quality": input_quality,
        "limitations": [],
        "metadata": {},
    }


def motionclip_payload(risk_level: str) -> dict:
    return {
        "model": {
            "profile_id": "carepd",
            "display_name": "CARE-PD",
            "status": "active_default",
            "architecture": "carepd_encoder_only_reference_difference_v1",
            "training_scope": "CARE-PD datasets",
            "checkpoint_epoch": 13,
            "web_interface_compatible": True,
            "clinical_risk_calibrated": False,
        },
        "metadata": {"window_count": 3},
        "healthy_distance": 0.06 if risk_level == "high" else 0.01,
        "risk_level": risk_level,
        "concepts": {},
        "explanation": "assessment",
    }


def assessed_payload(kinecal_level: str, motionclip_level: str = "low") -> dict:
    payload = assessment().model_dump(mode="python")
    payload.update(
        {
            "quality": {"passed": True, "reasons": []},
            "kinecal_model_status": "completed",
            "fall_risk_result": kinecal_payload(kinecal_level),
            "risk_model_status": "completed",
            "risk_result": motionclip_payload(motionclip_level),
        }
    )
    return payload


def test_low_kinecal_result_becomes_normal_and_does_not_trigger_report() -> None:
    value = FallRiskAssessment.model_validate(assessed_payload("low"))

    assert value.screening_result is not None
    assert value.screening_result.outcome == "normal"
    assert value.screening_result.normal_evidence == pytest.approx(0.9)
    assert value.screening_result.risk_evidence == pytest.approx(0.1)
    assert value.secondary_assessment_status == "not_triggered"
    assert value.risk_result is not None


@pytest.mark.parametrize("raw_level", ["medium", "high"])
def test_medium_and_high_kinecal_results_become_at_risk(raw_level: str) -> None:
    value = FallRiskAssessment.model_validate(assessed_payload(raw_level))

    assert value.screening_result is not None
    assert value.screening_result.outcome == "at_risk"
    assert value.secondary_assessment_status == "completed"


@pytest.mark.parametrize("raw_level", ["medium", "high"])
def test_at_risk_result_is_not_downgraded_to_review(raw_level: str) -> None:
    payload = assessed_payload(raw_level)
    payload["fall_risk_result"]["input_quality"] = "review"

    value = FallRiskAssessment.model_validate(payload)

    assert value.screening_result is not None
    assert value.screening_result.outcome == "at_risk"


def test_normal_screen_is_not_overridden_by_secondary_deviation() -> None:
    value = FallRiskAssessment.model_validate(assessed_payload("low", "high"))

    assert value.screening_result is not None
    assert value.screening_result.outcome == "normal"
    assert value.screening_result.discordant is False
    assert value.secondary_assessment_status == "not_triggered"


def test_low_confidence_or_limited_gait_does_not_become_normal() -> None:
    low_confidence = assessed_payload("low")
    low_confidence["fall_risk_result"]["input_quality"] = "review"
    reviewed = FallRiskAssessment.model_validate(low_confidence)
    assert reviewed.screening_result is not None
    assert reviewed.screening_result.outcome == "review_required"

    limited_gait = assessed_payload("medium")
    limited_gait["quality"] = {
        "passed": False,
        "complete_step_count": 2,
        "reasons": ["有效步数少于 6，步态汇总稳定性不足"],
    }
    limited = FallRiskAssessment.model_validate(limited_gait)
    assert limited.screening_result is not None
    assert limited.screening_result.outcome == "at_risk"
    assert limited.secondary_assessment_status == "review_required"
