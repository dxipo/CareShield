import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from careshield_contracts import (
    AssessmentArtifact,
    AssessmentQuality,
    FallRiskAssessment,
    FallRiskAssessmentCreate,
    PipelineState,
    PipelineStatus,
)

from app.core.config import FallRiskWorkerSettings
from app.services.assessment_service import (
    FallRiskAssessmentService,
    WorkerNotReadyError,
)
from app.adapters.command_pipeline import CommandPipeline
from app.adapters.media_validation import contains_decode_error


def settings(tmp_path: Path) -> FallRiskWorkerSettings:
    return FallRiskWorkerSettings(
        backend_internal_url="http://backend.invalid",
        shared_token="test-token",
        worker_id="test-risk-worker",
        worker_version="test",
        heartbeat_interval_seconds=10,
        data_root=tmp_path,
        channel_no=1,
        visionmd_python="/missing/python",
        visionmd_runner=Path("/missing/visionmd.py"),
        visionmd_project_root=Path("/missing/visionmd"),
        visionmd_metrabs_model_dir=Path("/missing/metrabs"),
        gvhmr_python="/missing/python",
        gvhmr_runner=Path("/missing/gvhmr.py"),
        gvhmr_project_root=Path("/missing/gvhmr"),
        gvhmr_checkpoints_root=tmp_path / "checkpoints",
        gvhmr_body_models_root=tmp_path / "body-models",
    )


def test_missing_runtimes_are_reported_and_jobs_are_rejected(tmp_path: Path) -> None:
    async def run() -> None:
        service = FallRiskAssessmentService(settings(tmp_path))
        status = service.status()
        assert status.ready is False
        assert status.gait_pipeline.status is PipelineStatus.NOT_CONFIGURED
        assert status.gvhmr_pipeline.status is PipelineStatus.NOT_CONFIGURED
        with pytest.raises(WorkerNotReadyError):
            await service.create(
                FallRiskAssessmentCreate(height_cm=170, capture_duration_seconds=15)
            )
        await service.close()

    asyncio.run(run())


def test_visionmd_readiness_requires_runtime_and_saved_model(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    project = tmp_path / "visionmd"
    model = tmp_path / "metrabs"
    runtime.mkdir()
    project.mkdir()
    model.mkdir()
    python = runtime / "python"
    runner = project / "run_rgb_to_28.py"
    python.touch()
    runner.touch()
    configured = replace(
        settings(tmp_path),
        visionmd_python=str(python),
        visionmd_runner=runner,
        visionmd_project_root=project,
        visionmd_metrabs_model_dir=model,
    )
    service = FallRiskAssessmentService(configured)
    assert service.status().ready is False
    (model / "saved_model.pb").touch()
    assert service.status().ready is True


def test_only_declared_processed_artifact_is_resolved(tmp_path: Path) -> None:
    async def run() -> None:
        service = FallRiskAssessmentService(settings(tmp_path))
        assessment_id = uuid4()
        overlay = service.store.directory(assessment_id) / "visionmd" / "visionmd_overlay.mp4"
        overlay.parent.mkdir(parents=True)
        overlay.write_bytes(b"video")
        assessment = FallRiskAssessment(
            assessment_id=assessment_id,
            status="partial",
            stage="complete",
            progress=1,
            height_cm=170,
            capture_duration_seconds=15,
            created_at=datetime.now(timezone.utc),
            gait_pipeline=PipelineState(status="completed"),
            gvhmr_pipeline=PipelineState(status="not_configured"),
            artifacts=[
                AssessmentArtifact(
                    artifact_id="gait-overlay",
                    kind="gait_overlay",
                    label="overlay",
                    media_type="video/mp4",
                )
            ],
        )
        await service.store.save(assessment)
        assert await service.artifact_path(assessment_id, "gait-overlay") == overlay
        await service.close()

    asyncio.run(run())


def test_pose_quality_exit_code_has_actionable_safe_error(tmp_path: Path) -> None:
    pipeline = CommandPipeline("VisionMD-Gait", "/runtime/python", tmp_path / "runner", tmp_path)
    assert "usable full-body walking" in pipeline.failure_message(20)
    assert "full-body" not in pipeline.failure_message(1)


def test_hevc_corruption_diagnostics_are_rejected() -> None:
    assert contains_decode_error(
        "[hevc] The cu_qp_delta -45 is outside the valid range"
    )
    assert contains_decode_error("Skipping invalid undecodable NALU: 1")
    assert not contains_decode_error("[hevc] Could not find ref with POC 17")
    assert contains_decode_error(
        "\n".join(["[hevc] Could not find ref with POC 17"] * 3)
    )
    assert not contains_decode_error("frame=225 fps=30 video decoded normally")


def test_pose_quality_gate_rejects_interpolation_dominated_result() -> None:
    quality = AssessmentQuality(
        pose_valid_ratio=0.004,
        full_body_visible_ratio=0.004,
        interpolated_frame_ratio=0.996,
        maximum_missing_gap_frames=131,
    )

    assert FallRiskAssessmentService._pose_quality_usable(quality) is False


def test_pose_quality_gate_accepts_observable_person() -> None:
    quality = AssessmentQuality(
        pose_valid_ratio=0.95,
        full_body_visible_ratio=0.9,
        interpolated_frame_ratio=0.05,
        maximum_missing_gap_frames=3,
    )

    assert FallRiskAssessmentService._pose_quality_usable(quality) is True


def test_gvhmr_artifacts_keep_skeleton_and_mesh_outputs_separate(tmp_path: Path) -> None:
    render_dir = tmp_path / "gvhmr" / "clip"
    render_dir.mkdir(parents=True)
    (render_dir / "1_incam.mp4").write_bytes(b"incamera")
    (tmp_path / "world_skeleton_3d.npz").write_bytes(b"skeleton")

    artifacts = FallRiskAssessmentService._gvhmr_artifacts(tmp_path)

    assert [item.artifact_id for item in artifacts] == [
        "gvhmr-incamera",
        "world-skeleton",
    ]


def test_gvhmr_rejects_concatenated_hmr2_checkpoint(tmp_path: Path) -> None:
    runtime = tmp_path / "gvhmr-runtime" / "bin"
    project = tmp_path / "gvhmr-project"
    checkpoints = tmp_path / "checkpoints"
    bodies = tmp_path / "body-models"
    runtime.mkdir(parents=True)
    project.mkdir()
    python = runtime / "python"
    runner = project / "runner.py"
    python.touch()
    runner.touch()
    for relative in (
        "gvhmr/gvhmr_siga24_release.ckpt",
        "hmr2/epoch=10-step=25000.ckpt",
        "vitpose/vitpose-h-multi-coco.pth",
        "yolo/yolov8x.pt",
    ):
        path = checkpoints / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not-a-valid-checkpoint")
    for relative in ("smpl/SMPL_NEUTRAL.pkl", "smplx/SMPLX_NEUTRAL.npz"):
        path = bodies / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"licensed-model")

    configured = replace(
        settings(tmp_path),
        gvhmr_python=str(python),
        gvhmr_runner=runner,
        gvhmr_project_root=project,
        gvhmr_checkpoints_root=checkpoints,
        gvhmr_body_models_root=bodies,
    )
    service = FallRiskAssessmentService(configured)

    assert service.status().gvhmr_pipeline.status is PipelineStatus.NOT_CONFIGURED
    assert "GVHMR official public checkpoints" in service.status().missing_requirements
