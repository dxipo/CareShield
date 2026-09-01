import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from careshield_contracts import FallRiskAssessmentCreate, FallRiskVideoAssessmentCreate

from app.core.config import AiRealtimeSettings
from app.services.fall_risk_service import FallRiskService, FallRiskServiceError


def settings() -> AiRealtimeSettings:
    return AiRealtimeSettings(
        app_env="test",
        redis_url="redis://unused",
        shared_token="private-worker-token",
        worker_ttl_seconds=30,
        latest_result_ttl_seconds=3600,
        fall_risk_worker_internal_url="http://risk-worker",
    )


def assessment_payload() -> dict:
    return {
        "assessment_id": str(uuid4()),
        "status": "queued",
        "stage": "waiting",
        "progress": 0,
        "device_id": None,
        "height_cm": 170,
        "capture_duration_seconds": 15,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "gait_pipeline": {"status": "waiting", "progress": 0, "message": None},
        "gvhmr_pipeline": {
            "status": "not_configured",
            "progress": 0,
            "message": "licensed body models are missing",
        },
        "quality": {"passed": False, "reasons": []},
        "gait_parameters": [],
        "artifacts": [],
        "risk_model_status": "not_installed",
        "risk_result": None,
        "error": None,
    }


def test_create_maps_contract_and_keeps_final_risk_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer private-worker-token"
        request_payload = await request.aread()
        assert b'"subject_name":"test subject"' in request_payload
        assert b'"sex":"female"' in request_payload
        assert b'"age":72' in request_payload
        payload = assessment_payload()
        payload.update({"subject_name": "test subject", "sex": "female", "age": 72})
        return httpx.Response(202, json=payload)

    async def run() -> None:
        service = FallRiskService(settings(), transport=httpx.MockTransport(handler))
        result = await service.create(
            FallRiskAssessmentCreate(
                subject_name="test subject",
                sex="female",
                age=72,
                height_cm=170,
                capture_duration_seconds=15,
            )
        )
        assert result.subject_name == "test subject"
        assert result.sex == "female"
        assert result.age == 72
        assert result.risk_model_status == "not_installed"
        assert result.risk_result is None
        await service.close()

    asyncio.run(run())


def test_uploaded_video_is_streamed_to_the_isolated_worker() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer private-worker-token"
        assert request.headers["content-type"] == "video/mp4"
        assert request.url.path == "/internal/assessments/upload"
        assert request.url.params["source_filename"] == "walking.mp4"
        assert request.url.params["subject_name"] == "test subject"
        assert request.url.params["sex"] == "male"
        assert request.url.params["age"] == "75"
        assert await request.aread() == b"real-video-bytes"
        payload = assessment_payload()
        payload["input_source"] = "uploaded_video"
        payload["source_filename"] = "walking.mp4"
        payload.update({"subject_name": "test subject", "sex": "male", "age": 75})
        return httpx.Response(202, json=payload)

    async def content():
        yield b"real-video-"
        yield b"bytes"

    async def run() -> None:
        service = FallRiskService(settings(), transport=httpx.MockTransport(handler))
        result = await service.create_from_video(
            FallRiskVideoAssessmentCreate(
                subject_name="test subject",
                sex="male",
                age=75,
                height_cm=170,
                capture_duration_seconds=38,
                source_filename="walking.mp4",
            ),
            content(),
            len(b"real-video-bytes"),
        )
        assert result.input_source == "uploaded_video"
        assert result.source_filename == "walking.mp4"
        assert result.subject_name == "test subject"
        assert result.sex == "male"
        assert result.age == 75
        await service.close()

    asyncio.run(run())


def test_worker_error_is_redacted() -> None:
    secret_response = "https://private.invalid/live?token=secret"

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=secret_response)

    async def run() -> None:
        service = FallRiskService(settings(), transport=httpx.MockTransport(handler))
        with pytest.raises(FallRiskServiceError) as captured:
            await service.status()
        message = str(captured.value)
        assert "secret" not in message
        assert "private-worker-token" not in message
        await service.close()

    asyncio.run(run())


def test_processed_artifact_is_streamed_with_internal_auth() -> None:
    assessment_id = uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer private-worker-token"
        assert str(assessment_id) in request.url.path
        return httpx.Response(200, content=b"processed-video", headers={"content-type": "video/mp4"})

    async def run() -> None:
        service = FallRiskService(settings(), transport=httpx.MockTransport(handler))
        response = await service.open_artifact(assessment_id, "gait-overlay")
        assert await response.aread() == b"processed-video"
        await response.aclose()
        await service.close()

    asyncio.run(run())


def test_existing_gvhmr_can_be_sent_to_core_model() -> None:
    payload = assessment_payload()
    payload["status"] = "completed"
    payload["gvhmr_pipeline"] = {"status": "completed", "progress": 1, "message": None}
    payload["risk_pipeline"] = {"status": "completed", "progress": 1, "message": None}
    payload["risk_model_status"] = "completed"
    payload["risk_result"] = {
        "model": {
            "profile_id": "carepd_four_dataset_explainable",
            "display_name": "CARE-PD model",
            "status": "active_default",
            "architecture": "carepd_encoder_only_reference_difference_v1",
            "training_scope": "four datasets",
            "checkpoint_epoch": 13,
            "web_interface_compatible": True,
            "clinical_risk_calibrated": False,
        },
        "metadata": {"window_count": 2},
        "healthy_distance": 0.03,
        "risk_level": None,
        "concepts": {
            "cadence": {
                "predicted_level": "normal",
                "predicted_level_id": 0,
                "probabilities": {"normal": 0.8, "abnormal": 0.2},
                "top1_probability": 0.8,
                "second_best_probability": 0.2,
                "margin": 0.6,
            }
        },
        "explanation": "research result",
    }
    assessment_id = payload["assessment_id"]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith(f"/{assessment_id}/risk-model")
        return httpx.Response(200, json=payload)

    async def run() -> None:
        service = FallRiskService(settings(), transport=httpx.MockTransport(handler))
        result = await service.run_risk_model(UUID(assessment_id))
        assert result.risk_result is not None
        assert result.risk_result.risk_level is None
        assert result.risk_result.healthy_distance == 0.03
        await service.close()

    asyncio.run(run())
