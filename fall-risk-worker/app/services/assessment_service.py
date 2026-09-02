from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from careshield_contracts import (
    AssessmentArtifact,
    AssessmentQuality,
    AssessmentStatus,
    FallRiskAssessment,
    FallRiskAssessmentCreate,
    FallRiskVideoAssessmentCreate,
    FallRiskWorkerStatus,
    PipelineState,
    PipelineStatus,
)

from app.adapters.backend_media import BackendMediaClient
from app.adapters.command_pipeline import CommandPipeline, PipelineExecutionError
from app.adapters.media_validation import (
    MediaIntegrityError,
    create_browser_preview,
    validate_video_capture,
)
from app.adapters.kinecal import KinecalRiskClient, KinecalRiskError
from app.adapters.motionclip import MotionClipClient, MotionClipError
from app.adapters.recorder import CaptureError, capture_video
from app.adapters.relay_recording import BufferedCaptureError, RelayRecordingClient
from app.adapters.risk_explanation import RiskExplanationClient
from app.core.config import FallRiskWorkerSettings
from app.services.job_store import AssessmentStore
from app.services.parameter_catalog import map_parameters


class WorkerNotReadyError(RuntimeError):
    pass


class AssessmentBusyError(RuntimeError):
    pass


class AssessmentArtifactNotFoundError(RuntimeError):
    pass


class RiskModelInputError(RuntimeError):
    pass


class VideoUploadError(RuntimeError):
    pass


class FallRiskAssessmentService:
    HMR2_CHECKPOINT_SIZE = 2_709_494_041
    MAX_VIDEO_BYTES = 512 * 1024 * 1024

    def __init__(self, settings: FallRiskWorkerSettings) -> None:
        self.settings = settings
        self.store = AssessmentStore(settings.data_root)
        self.media = BackendMediaClient(
            settings.backend_internal_url,
            settings.shared_token,
            settings.channel_no,
            relay_base_url=settings.media_relay_internal_url,
        )
        self.recordings = (
            RelayRecordingClient(settings.media_relay_playback_url)
            if settings.media_relay_playback_url
            else None
        )
        self.visionmd = CommandPipeline(
            "VisionMD-Gait",
            settings.visionmd_python,
            settings.visionmd_runner,
            settings.visionmd_project_root,
        )
        self.gvhmr = CommandPipeline(
            "GVHMR",
            settings.gvhmr_python,
            settings.gvhmr_runner,
            settings.gvhmr_project_root,
        )
        self.motionclip = MotionClipClient(
            settings.motionclip_internal_url,
            settings.shared_token,
        )
        self.kinecal = KinecalRiskClient(
            settings.kinecal_internal_url,
            settings.shared_token,
        )
        self.risk_explanation = RiskExplanationClient(
            enabled=settings.risk_explanation_enabled,
            base_url=settings.risk_explanation_base_url,
            model=settings.risk_explanation_model,
            timeout_seconds=settings.risk_explanation_timeout_seconds,
        )
        self._active_task: asyncio.Task | None = None
        self._active_id: UUID | None = None

    def status(self) -> FallRiskWorkerStatus:
        missing = self._missing_requirements()
        return FallRiskWorkerStatus(
            ready=self._visionmd_ready(),
            active_assessment_id=self._active_id,
            gait_pipeline=PipelineState(
                status=(
                    PipelineStatus.READY
                    if self._visionmd_ready()
                    else PipelineStatus.NOT_CONFIGURED
                ),
                message=(
                    None
                    if self._visionmd_ready()
                    else "VisionMD runtime or MeTRAbs model is not installed"
                ),
            ),
            gvhmr_pipeline=PipelineState(
                status=(
                    PipelineStatus.READY
                    if self._gvhmr_ready()
                    else PipelineStatus.NOT_CONFIGURED
                ),
                message=(None if self._gvhmr_ready() else "GVHMR runtime or licensed body models are missing"),
            ),
            risk_pipeline=PipelineState(
                status=(
                    PipelineStatus.READY
                    if self.motionclip.ready
                    else PipelineStatus.FAILED
                    if self.motionclip.configured
                    else PipelineStatus.NOT_CONFIGURED
                ),
                message=(None if self.motionclip.ready else "MotionCLIP worker is unavailable"),
            ),
            kinecal_pipeline=PipelineState(
                status=(
                    PipelineStatus.READY
                    if self.kinecal.ready
                    else PipelineStatus.FAILED
                    if self.kinecal.configured
                    else PipelineStatus.NOT_CONFIGURED
                ),
                message=(None if self.kinecal.ready else "KINECAL risk worker is unavailable"),
            ),
            missing_requirements=missing,
        )

    async def create(self, request: FallRiskAssessmentCreate) -> FallRiskAssessment:
        if not self._visionmd_ready():
            raise WorkerNotReadyError("VisionMD-Gait runtime is not configured")
        if self._active_task is not None and not self._active_task.done():
            raise AssessmentBusyError("Another fall-risk assessment is already running")
        await self.motionclip.refresh_health()
        await self.kinecal.refresh_health()
        assessment = self._new_assessment(
            subject_name=request.subject_name,
            sex=request.sex,
            age=request.age,
            height_cm=request.height_cm,
            duration_seconds=request.capture_duration_seconds,
            device_id=request.device_id,
            input_source="camera",
        )
        await self.store.save(assessment)
        self._active_id = assessment.assessment_id
        self._active_task = asyncio.create_task(self._run(assessment), name="fall-risk-assessment")
        return assessment

    async def create_from_video(
        self,
        request: FallRiskVideoAssessmentCreate,
        chunks: AsyncIterable[bytes],
        content_length: int | None,
    ) -> FallRiskAssessment:
        if not self._visionmd_ready():
            raise WorkerNotReadyError("VisionMD-Gait runtime is not configured")
        if self._active_task is not None and not self._active_task.done():
            raise AssessmentBusyError("Another fall-risk assessment is already running")
        if content_length is not None and content_length > self.MAX_VIDEO_BYTES:
            raise VideoUploadError("Video upload exceeds the 512 MB limit")
        await self.motionclip.refresh_health()
        await self.kinecal.refresh_health()
        safe_filename = Path(request.source_filename).name.replace("\n", " ").replace("\r", " ")
        if not safe_filename.lower().endswith(".mp4"):
            raise VideoUploadError("Only MP4 video uploads are supported")
        assessment = self._new_assessment(
            subject_name=request.subject_name,
            sex=request.sex,
            age=request.age,
            height_cm=request.height_cm,
            duration_seconds=request.capture_duration_seconds,
            device_id=None,
            input_source="uploaded_video",
            source_filename=safe_filename,
        ).model_copy(
            update={
                "status": AssessmentStatus.CAPTURING,
                "stage": "上传评估视频",
                "progress": 0.03,
                "started_at": datetime.now(timezone.utc),
                "capture_started_at": datetime.now(timezone.utc),
            }
        )
        await self.store.save(assessment)
        self._active_id = assessment.assessment_id
        directory = self.store.directory(assessment.assessment_id)
        source = directory / "source.mp4"
        temporary = directory / "source.mp4.upload"
        received = 0
        try:
            with temporary.open("wb") as destination:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > self.MAX_VIDEO_BYTES:
                        raise VideoUploadError("Video upload exceeds the 512 MB limit")
                    destination.write(chunk)
            if received == 0:
                raise VideoUploadError("Uploaded video is empty")
            await validate_video_capture(temporary)
            temporary.replace(source)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            safe_error = str(exc) if isinstance(exc, (VideoUploadError, MediaIntegrityError)) else "Video upload failed"
            assessment = assessment.model_copy(
                update={
                    "status": AssessmentStatus.FAILED,
                    "stage": "视频导入失败",
                    "completed_at": datetime.now(timezone.utc),
                    "error": safe_error,
                }
            )
            await self.store.save(assessment)
            self._active_id = None
            raise VideoUploadError(safe_error) from exc
        self._active_task = asyncio.create_task(self._run(assessment), name="fall-risk-video-assessment")
        return assessment

    def _new_assessment(
        self,
        *,
        subject_name: str | None,
        sex: str | None,
        age: int | None,
        height_cm: float,
        duration_seconds: int,
        device_id: str | None,
        input_source: str,
        source_filename: str | None = None,
    ) -> FallRiskAssessment:
        now = datetime.now(timezone.utc)
        gvhmr_ready = self._gvhmr_ready()
        risk_ready = gvhmr_ready and self.motionclip.ready
        kinecal_ready = gvhmr_ready and self.kinecal.ready
        return FallRiskAssessment(
            assessment_id=uuid4(),
            status=AssessmentStatus.QUEUED,
            stage="等待采集" if input_source == "camera" else "等待视频导入",
            device_id=device_id,
            input_source=input_source,
            source_filename=source_filename,
            subject_name=subject_name,
            sex=sex,
            age=age,
            height_cm=height_cm,
            capture_duration_seconds=duration_seconds,
            created_at=now,
            gait_pipeline=PipelineState(status=PipelineStatus.WAITING),
            gvhmr_pipeline=PipelineState(
                status=PipelineStatus.WAITING if gvhmr_ready else PipelineStatus.NOT_CONFIGURED,
                message=None if gvhmr_ready else "授权人体模型或 GVHMR 环境未就绪",
            ),
            risk_pipeline=PipelineState(
                status=PipelineStatus.WAITING if risk_ready else PipelineStatus.NOT_CONFIGURED,
                message=None if risk_ready else "MotionCLIP 需要可用的 GVHMR 参数与独立模型 Worker",
            ),
            risk_model_status="waiting" if risk_ready else "not_configured",
            kinecal_pipeline=PipelineState(
                status=PipelineStatus.WAITING if kinecal_ready else PipelineStatus.NOT_CONFIGURED,
                message=None if kinecal_ready else "KINECAL 风险分类需要世界系 3D 骨架与独立模型 Worker",
            ),
            kinecal_model_status="waiting" if kinecal_ready else "not_configured",
        )

    async def close(self) -> None:
        if self._active_task is not None:
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass
        await self.media.close()
        await self.motionclip.close()
        await self.kinecal.close()
        await self.risk_explanation.close()
        if self.recordings is not None:
            await self.recordings.close()

    async def artifact_path(self, assessment_id: UUID, artifact_id: str) -> Path:
        assessment = await self.store.get(assessment_id)
        if not any(item.artifact_id == artifact_id for item in assessment.artifacts):
            raise AssessmentArtifactNotFoundError("Assessment artifact not found")
        directory = self.store.directory(assessment_id)
        if artifact_id == "source-video":
            preview = directory / "source-preview.mp4"
            candidate = preview if preview.is_file() else directory / "source.mp4"
        elif artifact_id == "gait-overlay":
            candidate = directory / "visionmd" / "visionmd_overlay.mp4"
        elif artifact_id == "gvhmr-incamera":
            matches = list((directory / "gvhmr").rglob("1_incam.mp4"))
            candidate = matches[0] if len(matches) == 1 else Path()
        elif artifact_id == "gvhmr-global":
            matches = list((directory / "gvhmr").rglob("2_global.mp4"))
            candidate = matches[0] if len(matches) == 1 else Path()
        else:
            raise AssessmentArtifactNotFoundError("Assessment artifact is not viewable")
        if not candidate.is_file() or directory not in candidate.parents:
            raise AssessmentArtifactNotFoundError("Assessment artifact not found")
        return candidate

    async def run_risk_model(self, assessment_id: UUID) -> FallRiskAssessment:
        if self._active_task is not None and not self._active_task.done():
            raise AssessmentBusyError("Another fall-risk assessment is already running")
        assessment = await self.store.get(assessment_id)
        await self.motionclip.refresh_health()
        await self.kinecal.refresh_health()
        if not self.motionclip.ready and not self.kinecal.ready:
            raise WorkerNotReadyError("Fall-risk model workers are unavailable")
        parameters = self.store.directory(assessment_id) / "gvhmr" / "smplx_global_params.npz"
        skeleton = self.store.directory(assessment_id) / "gvhmr" / "world_skeleton_3d.npz"
        if (
            assessment.gvhmr_pipeline.status is not PipelineStatus.COMPLETED
            or (self.motionclip.ready and not parameters.is_file())
            or (self.kinecal.ready and not skeleton.is_file())
        ):
            raise RiskModelInputError("Completed GVHMR skeleton and parameters are required")
        rerun_update = {
            "status": AssessmentStatus.PROCESSING_RISK,
            "stage": "运行跌倒风险与神经运动分析",
            "progress": 0.92,
            "risk_pipeline": PipelineState(
                status=PipelineStatus.RUNNING if self.motionclip.ready else PipelineStatus.NOT_CONFIGURED,
                progress=0.2 if self.motionclip.ready else 0.0,
            ),
            "risk_model_status": "running" if self.motionclip.ready else "not_configured",
            "kinecal_pipeline": PipelineState(
                status=PipelineStatus.RUNNING if self.kinecal.ready else PipelineStatus.NOT_CONFIGURED,
                progress=0.2 if self.kinecal.ready else 0.0,
            ),
            "kinecal_model_status": "running" if self.kinecal.ready else "not_configured",
            "error": None,
        }
        if self.motionclip.ready:
            rerun_update["risk_result"] = None
        if self.kinecal.ready:
            rerun_update["fall_risk_result"] = None
        assessment = assessment.model_copy(update=rerun_update)
        await self.store.save(assessment)
        if self.kinecal.ready:
            try:
                result = await self.kinecal.predict(assessment_id)
                assessment = assessment.model_copy(update={
                    "kinecal_pipeline": PipelineState(status=PipelineStatus.COMPLETED, progress=1.0),
                    "kinecal_model_status": "completed",
                    "fall_risk_result": result,
                })
            except KinecalRiskError as exc:
                assessment = assessment.model_copy(update={
                    "kinecal_pipeline": PipelineState(status=PipelineStatus.FAILED, message=str(exc)),
                    "kinecal_model_status": "failed",
                })
        if self.motionclip.ready:
            try:
                result = await self.motionclip.predict(assessment_id)
                result = await self.risk_explanation.explain(result)
                assessment = assessment.model_copy(update={
                    "risk_pipeline": PipelineState(status=PipelineStatus.COMPLETED, progress=1.0),
                    "risk_model_status": "completed",
                    "risk_result": result,
                })
            except MotionClipError as exc:
                assessment = assessment.model_copy(update={
                    "risk_pipeline": PipelineState(status=PipelineStatus.FAILED, message=str(exc)),
                    "risk_model_status": "failed",
                })
        complete = (
            assessment.kinecal_pipeline.status is PipelineStatus.COMPLETED
            and assessment.risk_pipeline.status is PipelineStatus.COMPLETED
        )
        assessment = assessment.model_copy(update={
            "status": AssessmentStatus.COMPLETED if complete else AssessmentStatus.PARTIAL,
            "stage": "跌倒风险与神经运动分析完成" if complete else "部分风险分析结果可用",
            "progress": 1.0,
        })
        await self.store.save(assessment)
        return assessment

    async def _run(self, assessment: FallRiskAssessment) -> None:
        try:
            directory = self.store.directory(assessment.assessment_id)
            source = directory / "source.mp4"
            if assessment.input_source == "camera":
                assessment = assessment.model_copy(
                    update={
                        "status": AssessmentStatus.CAPTURING,
                        "stage": "按触发时刻采集步态视频",
                        "progress": 0.05,
                        "started_at": datetime.now(timezone.utc),
                        "capture_started_at": assessment.created_at,
                    }
                )
                await self.store.save(assessment)
                device = await self.media.select_device(assessment.device_id)
                if self.recordings is not None:
                    await self.recordings.capture(
                        source,
                        triggered_at=assessment.created_at,
                        duration_seconds=assessment.capture_duration_seconds,
                    )
                else:
                    stream = await self.media.get_stream(device)
                    await capture_video(
                        stream.playback_url,
                        source,
                        assessment.capture_duration_seconds,
                    )
                await validate_video_capture(source)
                device_id = device.id
                capture_completed_at = assessment.created_at + timedelta(
                    seconds=assessment.capture_duration_seconds
                )
            else:
                if not source.is_file():
                    raise MediaIntegrityError("Uploaded video is unavailable")
                await create_browser_preview(source, directory / "source-preview.mp4")
                device_id = None
                capture_completed_at = datetime.now(timezone.utc)
            source_artifact = AssessmentArtifact(
                artifact_id="source-video",
                kind="source_video",
                label=(
                    "本次评估采集视频"
                    if assessment.input_source == "camera"
                    else "本次评估上传视频"
                ),
                media_type="video/mp4",
            )

            gait_output = directory / "visionmd"
            processing_started_at = datetime.now(timezone.utc)
            assessment = assessment.model_copy(
                update={
                    "device_id": device_id,
                    "status": AssessmentStatus.PROCESSING_GAIT,
                    "stage": "计算步态事件与 28 项参数",
                    "progress": 0.30,
                    "capture_completed_at": capture_completed_at,
                    "processing_started_at": processing_started_at,
                    "gait_pipeline": PipelineState(status=PipelineStatus.RUNNING, progress=0.1),
                    "artifacts": [source_artifact],
                }
            )
            await self.store.save(assessment)
            await self.visionmd.run(
                [
                    str(source),
                    "--height-cm",
                    str(assessment.height_cm),
                    "--output",
                    str(gait_output),
                ]
            )
            parameters, quality = self._load_gait_results(gait_output)
            analysis_source = gait_output / "analysis_clip.mp4"
            if not analysis_source.is_file():
                raise PipelineExecutionError(
                    "VisionMD-Gait completed without a selected analysis clip"
                )
            gait_artifacts = self._visionmd_artifacts(gait_output)
            assessment = assessment.model_copy(
                update={
                    "progress": 0.70,
                    "gait_pipeline": PipelineState(status=PipelineStatus.COMPLETED, progress=1.0),
                    "gait_parameters": parameters,
                    "quality": quality,
                    "artifacts": assessment.artifacts + gait_artifacts,
                }
            )
            await self.store.save(assessment)

            if not self._pose_quality_usable(quality):
                assessment = assessment.model_copy(
                    update={
                        "status": AssessmentStatus.QUALITY_REVIEW,
                        "stage": "人体姿态质量不足，请重新采集",
                        "progress": 1.0,
                        "completed_at": datetime.now(timezone.utc),
                        "gvhmr_pipeline": PipelineState(
                            status=PipelineStatus.SKIPPED,
                            message="输入姿态质量不足，未运行 GVHMR / SMPL-X",
                        ),
                        "risk_pipeline": PipelineState(
                            status=PipelineStatus.SKIPPED,
                            message="输入姿态质量不足，未运行 MotionCLIP",
                        ),
                        "risk_model_status": "skipped",
                        "kinecal_pipeline": PipelineState(
                            status=PipelineStatus.SKIPPED,
                            message="输入姿态质量不足，未运行 KINECAL 风险分类",
                        ),
                        "kinecal_model_status": "skipped",
                    }
                )
                await self.store.save(assessment)
                return

            if self._gvhmr_ready():
                assessment = assessment.model_copy(
                    update={
                        "status": AssessmentStatus.PROCESSING_GVHMR,
                        "stage": "恢复世界系 3D 骨架",
                        "progress": 0.75,
                        "gvhmr_pipeline": PipelineState(status=PipelineStatus.RUNNING, progress=0.1),
                    }
                )
                await self.store.save(assessment)
                gvhmr_output = directory / "gvhmr"
                await self.gvhmr.run(
                    [str(analysis_source), "--output", str(gvhmr_output)]
                )
                assessment = assessment.model_copy(
                    update={
                        "gvhmr_pipeline": PipelineState(status=PipelineStatus.COMPLETED, progress=1.0),
                        "artifacts": assessment.artifacts + self._gvhmr_artifacts(gvhmr_output),
                    }
                )
                if self.kinecal.ready:
                    assessment = assessment.model_copy(
                        update={
                            "status": AssessmentStatus.PROCESSING_RISK,
                            "stage": "评估跌倒风险等级",
                            "progress": 0.88,
                            "kinecal_pipeline": PipelineState(
                                status=PipelineStatus.RUNNING,
                                progress=0.2,
                            ),
                            "kinecal_model_status": "running",
                        }
                    )
                    await self.store.save(assessment)
                    try:
                        fall_risk_result = await self.kinecal.predict(assessment.assessment_id)
                        assessment = assessment.model_copy(
                            update={
                                "kinecal_pipeline": PipelineState(
                                    status=PipelineStatus.COMPLETED,
                                    progress=1.0,
                                ),
                                "kinecal_model_status": "completed",
                                "fall_risk_result": fall_risk_result,
                            }
                        )
                    except KinecalRiskError as exc:
                        assessment = assessment.model_copy(
                            update={
                                "kinecal_pipeline": PipelineState(
                                    status=PipelineStatus.FAILED,
                                    message=str(exc),
                                ),
                                "kinecal_model_status": "failed",
                            }
                        )
                if self.motionclip.ready:
                    assessment = assessment.model_copy(
                        update={
                            "status": AssessmentStatus.PROCESSING_RISK,
                            "stage": "运行 MotionCLIP 可解释风险模型",
                            "progress": 0.92,
                            "risk_pipeline": PipelineState(
                                status=PipelineStatus.RUNNING,
                                progress=0.2,
                            ),
                            "risk_model_status": "running",
                        }
                    )
                    await self.store.save(assessment)
                    try:
                        risk_result = await self.motionclip.predict(assessment.assessment_id)
                        risk_result = await self.risk_explanation.explain(risk_result)
                        assessment = assessment.model_copy(
                            update={
                                "risk_pipeline": PipelineState(
                                    status=PipelineStatus.COMPLETED,
                                    progress=1.0,
                                ),
                                "risk_model_status": "completed",
                                "risk_result": risk_result,
                            }
                        )
                    except MotionClipError as exc:
                        assessment = assessment.model_copy(
                            update={
                                "risk_pipeline": PipelineState(
                                    status=PipelineStatus.FAILED,
                                    message=str(exc),
                                ),
                                "risk_model_status": "failed",
                            }
                        )

            assessment = assessment.model_copy(
                update={
                    "status": (
                        AssessmentStatus.COMPLETED
                        if (
                            assessment.risk_pipeline.status is PipelineStatus.COMPLETED
                            and assessment.kinecal_pipeline.status is PipelineStatus.COMPLETED
                        )
                        else AssessmentStatus.PARTIAL
                    ),
                    "stage": (
                        "跌倒风险与神经运动分析完成"
                        if (
                            assessment.risk_pipeline.status is PipelineStatus.COMPLETED
                            and assessment.kinecal_pipeline.status is PipelineStatus.COMPLETED
                        )
                        else "特征提取完成，部分风险分析结果可用"
                    ),
                    "progress": 1.0,
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            await self.store.save(assessment)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            safe_error = (
                str(exc)
                if isinstance(
                    exc,
                    (
                        CaptureError,
                        BufferedCaptureError,
                        MediaIntegrityError,
                        PipelineExecutionError,
                    ),
                )
                else "Fall-risk assessment failed"
            )
            gait_pipeline = assessment.gait_pipeline
            if gait_pipeline.status is PipelineStatus.WAITING:
                gait_pipeline = PipelineState(
                    status=PipelineStatus.SKIPPED,
                    message="输入视频未就绪，VisionMD-Gait 未启动",
                )
            elif gait_pipeline.status is PipelineStatus.RUNNING:
                gait_pipeline = PipelineState(
                    status=PipelineStatus.FAILED,
                    message=safe_error,
                )
            gvhmr_pipeline = assessment.gvhmr_pipeline
            if gvhmr_pipeline.status is PipelineStatus.WAITING:
                gvhmr_pipeline = PipelineState(
                    status=PipelineStatus.SKIPPED,
                    message="输入视频未通过校验，GVHMR / SMPL-X 未启动",
                )
            elif gvhmr_pipeline.status is PipelineStatus.RUNNING:
                gvhmr_pipeline = PipelineState(
                    status=PipelineStatus.FAILED,
                    message="GVHMR pipeline failed",
                )
            risk_pipeline = assessment.risk_pipeline
            if risk_pipeline.status is PipelineStatus.WAITING:
                risk_pipeline = PipelineState(
                    status=PipelineStatus.SKIPPED,
                    message="GVHMR 参数未就绪，MotionCLIP 未启动",
                )
            elif risk_pipeline.status is PipelineStatus.RUNNING:
                risk_pipeline = PipelineState(
                    status=PipelineStatus.FAILED,
                    message="MotionCLIP inference failed",
                )
            kinecal_pipeline = assessment.kinecal_pipeline
            if kinecal_pipeline.status is PipelineStatus.WAITING:
                kinecal_pipeline = PipelineState(
                    status=PipelineStatus.SKIPPED,
                    message="世界系骨架未就绪，KINECAL 风险分类未启动",
                )
            elif kinecal_pipeline.status is PipelineStatus.RUNNING:
                kinecal_pipeline = PipelineState(
                    status=PipelineStatus.FAILED,
                    message="KINECAL fall-risk inference failed",
                )
            assessment = assessment.model_copy(
                update={
                    "status": AssessmentStatus.FAILED,
                    "stage": "评估失败",
                    "completed_at": datetime.now(timezone.utc),
                    "error": safe_error,
                    "gait_pipeline": gait_pipeline,
                    "gvhmr_pipeline": gvhmr_pipeline,
                    "risk_pipeline": risk_pipeline,
                    "kinecal_pipeline": kinecal_pipeline,
                    "risk_model_status": (
                        "failed"
                        if risk_pipeline.status is PipelineStatus.FAILED
                        else assessment.risk_model_status
                    ),
                    "kinecal_model_status": (
                        "failed"
                        if kinecal_pipeline.status is PipelineStatus.FAILED
                        else assessment.kinecal_model_status
                    ),
                }
            )
            await self.store.save(assessment)
        finally:
            self._active_id = None

    def _load_gait_results(self, output: Path):
        parameter_path = output / "gait_parameters_28.json"
        event_path = output / "gait_events.json"
        if not parameter_path.is_file() or not event_path.is_file():
            raise PipelineExecutionError("VisionMD-Gait completed without required result files")
        parameter_payload = json.loads(parameter_path.read_text(encoding="utf-8"))
        event_payload = json.loads(event_path.read_text(encoding="utf-8"))
        values = parameter_payload.get("gait_parameters_28")
        if not isinstance(values, dict):
            raise PipelineExecutionError("VisionMD-Gait parameter result is invalid")
        left_down = event_payload.get("left_down", [])
        right_down = event_payload.get("right_down", [])
        left_up = event_payload.get("left_up", [])
        right_up = event_payload.get("right_up", [])
        hs_count = len(left_down) + len(right_down)
        to_count = len(left_up) + len(right_up)
        complete_steps = max(0, hs_count - 1)
        reasons = []
        if complete_steps < 6:
            reasons.append("有效步数少于 6，步态汇总稳定性不足")
        unavailable_count = sum(value is None for value in values.values())
        if unavailable_count:
            reasons.append(f"{unavailable_count} 项参数因事件不足无法计算")
        raw_quality = parameter_payload.get("quality", {})
        pose_valid_ratio = raw_quality.get("pose_valid_ratio")
        full_body_visible_ratio = raw_quality.get("full_body_visible_ratio")
        interpolated_frame_ratio = raw_quality.get("interpolated_frame_ratio")
        maximum_missing_gap = raw_quality.get("maximum_missing_gap_frames")
        maximum_missing_gap_seconds = raw_quality.get("maximum_missing_gap_seconds")
        video_duration = raw_quality.get("video_duration_seconds")
        original_video_duration = raw_quality.get("original_video_duration_seconds")
        selected_start = raw_quality.get("selected_start_seconds")
        selected_end = raw_quality.get("selected_end_seconds")
        discarded_duration = raw_quality.get("discarded_duration_seconds")
        if isinstance(pose_valid_ratio, (int, float)) and pose_valid_ratio < 0.8:
            reasons.append("有效人体姿态帧比例低于 80%")
        if isinstance(full_body_visible_ratio, (int, float)) and full_body_visible_ratio < 0.8:
            reasons.append("全身完整可见帧比例低于 80%")
        if isinstance(interpolated_frame_ratio, (int, float)) and interpolated_frame_ratio > 0.2:
            reasons.append("分析片段插值帧比例超过 20%")
        if (
            isinstance(maximum_missing_gap_seconds, (int, float))
            and maximum_missing_gap_seconds > 1.0
        ):
            reasons.append(
                f"分析片段连续姿态缺失 {maximum_missing_gap_seconds:.2f} 秒，超过 1.00 秒"
            )
        quality = AssessmentQuality(
            passed=complete_steps >= 6 and unavailable_count == 0 and not reasons,
            source_fps=(
                float(parameter_payload["fps"])
                if isinstance(parameter_payload.get("fps"), (int, float))
                else None
            ),
            video_duration_seconds=(
                float(video_duration)
                if isinstance(video_duration, (int, float))
                else None
            ),
            original_video_duration_seconds=(
                float(original_video_duration)
                if isinstance(original_video_duration, (int, float))
                else None
            ),
            selected_start_seconds=(
                float(selected_start)
                if isinstance(selected_start, (int, float))
                else None
            ),
            selected_end_seconds=(
                float(selected_end)
                if isinstance(selected_end, (int, float))
                else None
            ),
            discarded_duration_seconds=(
                float(discarded_duration)
                if isinstance(discarded_duration, (int, float))
                else None
            ),
            full_body_visible_ratio=(
                float(full_body_visible_ratio)
                if isinstance(full_body_visible_ratio, (int, float))
                else None
            ),
            pose_valid_ratio=(
                float(pose_valid_ratio)
                if isinstance(pose_valid_ratio, (int, float))
                else None
            ),
            interpolated_frame_ratio=(
                float(interpolated_frame_ratio)
                if isinstance(interpolated_frame_ratio, (int, float))
                else None
            ),
            maximum_missing_gap_frames=(
                int(maximum_missing_gap)
                if isinstance(maximum_missing_gap, int)
                else None
            ),
            maximum_missing_gap_seconds=(
                float(maximum_missing_gap_seconds)
                if isinstance(maximum_missing_gap_seconds, (int, float))
                else (
                    float(maximum_missing_gap / parameter_payload["fps"])
                    if isinstance(maximum_missing_gap, int)
                    and isinstance(parameter_payload.get("fps"), (int, float))
                    and parameter_payload["fps"] > 0
                    else None
                )
            ),
            heel_strike_count=hs_count,
            toe_off_count=to_count,
            complete_step_count=complete_steps,
            reasons=reasons,
        )
        return map_parameters(values), quality

    @staticmethod
    def _pose_quality_usable(quality: AssessmentQuality) -> bool:
        return bool(
            quality.pose_valid_ratio is not None
            and quality.pose_valid_ratio >= 0.8
            and quality.full_body_visible_ratio is not None
            and quality.full_body_visible_ratio >= 0.8
            and quality.interpolated_frame_ratio is not None
            and quality.interpolated_frame_ratio <= 0.2
            and quality.maximum_missing_gap_frames is not None
            and quality.maximum_missing_gap_seconds is not None
            and quality.maximum_missing_gap_seconds <= 1.0
        )

    @staticmethod
    def _visionmd_artifacts(output: Path) -> list[AssessmentArtifact]:
        if not (output / "visionmd_overlay.mp4").is_file():
            return []
        return [
            AssessmentArtifact(
                artifact_id="gait-overlay",
                kind="gait_overlay",
                label="MeTRAbs 骨架与步态处理视频",
                media_type="video/mp4",
            )
        ]

    @staticmethod
    def _gvhmr_artifacts(output: Path) -> list[AssessmentArtifact]:
        candidates = (
            (
                "gvhmr-incamera",
                "gvhmr_incamera",
                "原景 SMPL-X 人体网格",
                "video/mp4",
                any(output.rglob("1_incam.mp4")),
            ),
            (
                "gvhmr-global",
                "gvhmr_global",
                "SMPL-X 世界系动作视图",
                "video/mp4",
                any(output.rglob("2_global.mp4")),
            ),
            (
                "world-skeleton",
                "world_skeleton",
                "世界系 3D 骨架",
                "application/octet-stream",
                (output / "world_skeleton_3d.npz").is_file(),
            ),
        )
        artifacts = []
        for artifact_id, kind, label, media_type, available in candidates:
            if available:
                artifacts.append(
                    AssessmentArtifact(
                        artifact_id=artifact_id,
                        kind=kind,
                        label=label,
                        media_type=media_type,
                    )
                )
        return artifacts

    def _gvhmr_ready(self) -> bool:
        checkpoints = self.settings.gvhmr_checkpoints_root
        bodies = self.settings.gvhmr_body_models_root
        return bool(
            self.gvhmr.configured
            and (checkpoints / "gvhmr/gvhmr_siga24_release.ckpt").is_file()
            and self._hmr2_checkpoint_valid()
            and (checkpoints / "vitpose/vitpose-h-multi-coco.pth").is_file()
            and (checkpoints / "yolo/yolov8x.pt").is_file()
            and (bodies / "smplx/SMPLX_NEUTRAL.npz").is_file()
            and (bodies / "smpl/SMPL_NEUTRAL.pkl").is_file()
        )

    def _visionmd_ready(self) -> bool:
        model = self.settings.visionmd_metrabs_model_dir
        return bool(
            self.visionmd.configured
            and model.is_dir()
            and (model / "saved_model.pb").is_file()
        )

    def _missing_requirements(self) -> list[str]:
        missing = []
        if not self._visionmd_ready():
            missing.append("VisionMD-Gait runtime, runner, and MeTRAbs SavedModel")
        if not self.gvhmr.configured:
            missing.append("GVHMR independent Python/CUDA runtime")
        checkpoints = self.settings.gvhmr_checkpoints_root
        required_checkpoints = (
            "gvhmr/gvhmr_siga24_release.ckpt",
            "hmr2/epoch=10-step=25000.ckpt",
            "vitpose/vitpose-h-multi-coco.pth",
            "yolo/yolov8x.pt",
        )
        if (
            any(not (checkpoints / item).is_file() for item in required_checkpoints)
            or not self._hmr2_checkpoint_valid()
        ):
            missing.append("GVHMR official public checkpoints")
        bodies = self.settings.gvhmr_body_models_root
        if not (bodies / "smpl/SMPL_NEUTRAL.pkl").is_file():
            missing.append("Licensed SMPL neutral body model")
        if not (bodies / "smplx/SMPLX_NEUTRAL.npz").is_file():
            missing.append("Licensed SMPL-X neutral body model")
        if not self.motionclip.ready:
            missing.append("MotionCLIP model worker or checkpoint")
        if not self.kinecal.ready:
            missing.append("KINECAL ST-GCN++ model worker or checkpoint")
        return missing

    async def refresh_motionclip(self) -> bool:
        motionclip_ready = await self.motionclip.refresh_health()
        await self.kinecal.refresh_health()
        return motionclip_ready

    def _hmr2_checkpoint_valid(self) -> bool:
        checkpoint = (
            self.settings.gvhmr_checkpoints_root
            / "hmr2/epoch=10-step=25000.ckpt"
        )
        return bool(
            checkpoint.is_file()
            and checkpoint.stat().st_size == self.HMR2_CHECKPOINT_SIZE
        )
