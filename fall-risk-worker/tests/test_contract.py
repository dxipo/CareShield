from datetime import datetime, timezone
from uuid import uuid4

import pytest
from careshield_contracts import (
    AssessmentStatus,
    FallRiskAssessment,
    PipelineState,
    PipelineStatus,
    FallRiskVideoAssessmentCreate,
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
        height_cm=168,
        capture_duration_seconds=39,
        source_filename="walking.mp4",
    )
    assert request.source_filename == "walking.mp4"
    payload = assessment().model_copy(
        update={"input_source": "uploaded_video", "source_filename": "walking.mp4"}
    )
    assert payload.input_source == "uploaded_video"

    with pytest.raises(ValidationError):
        FallRiskVideoAssessmentCreate(
            height_cm=168,
            capture_duration_seconds=61,
            source_filename="walking.mp4",
        )


def test_quality_gate_can_explicitly_skip_the_risk_model() -> None:
    value = assessment().model_copy(update={"risk_model_status": "skipped"})
    assert value.risk_model_status == "skipped"
