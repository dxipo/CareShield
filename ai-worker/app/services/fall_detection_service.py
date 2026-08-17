from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from careshield_contracts import AlgorithmResult, AlgorithmTask, RiskLevel

from app.core.config import WorkerSettings
from app.fall_detection.detector import FallDecision, FallState, TemporalFallDetector
from app.fall_detection.features import FallFeatureExtractor
from app.fall_detection.pose_estimator import PoseModelError, UltralyticsPoseEstimator
from app.fall_detection.publish_policy import FallPublishPolicy
from app.media.backend_client import BackendMediaClient, MediaBackendError, MediaDevice
from app.media.frame_sampler import FrameSampler
from app.media.reader import MediaReader
from app.publisher.result_publisher import PublishError, ResultPublisher


logger = logging.getLogger(__name__)


class FallDetectionService:
    MODEL_ID = "pose-fall-baseline"
    MODEL_VERSION = "m5-v1"

    def __init__(
        self,
        settings: WorkerSettings,
        publisher: ResultPublisher,
        media_client: BackendMediaClient,
        *,
        estimator: UltralyticsPoseEstimator | None = None,
    ) -> None:
        self.settings = settings
        self.publisher = publisher
        self.media_client = media_client
        self.estimator = estimator or UltralyticsPoseEstimator(settings)
        self.detector = TemporalFallDetector(settings.fall_config)
        self.extractor = FallFeatureExtractor()
        self.sampler = FrameSampler(settings.fall_config.input_fps)
        self.policy = FallPublishPolicy(
            settings.fall_config.result_heartbeat_seconds,
            settings.fall_config.significant_score_delta,
        )
        self.reader = MediaReader(
            media_client,
            reconnect_seconds=settings.media_reconnect_seconds,
            status_callback=self._set_stream_status,
        )
        self.capability = "starting" if settings.fall_enabled else "not_installed"
        self.detector_status = "starting" if settings.fall_enabled else "disabled"
        self.stream_status = "not_connected"
        self.last_error: str | None = None
        self.device: MediaDevice | None = None
        self.last_result_at: datetime | None = None
        self.source_fps: float | None = None
        self.sampled_fps: float | None = None
        self.publish_rate: float | None = None
        self._task: asyncio.Task | None = None
        self._sample_count = 0
        self._publish_count = 0
        self._metrics_started_at: float | None = None
        self._last_empty_publish = 0.0

    async def start(self) -> None:
        if not self.settings.fall_enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="fall-detection")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.media_client.close()

    def runtime_metadata(self) -> dict:
        return {
            "fall_detection": {
                "status": self.detector_status,
                "stream_status": self.stream_status,
                "device_id": self.device.id if self.device else None,
                "device_model": self.device.model if self.device else None,
                "model": self.settings.fall_model_name,
                "model_version": self.MODEL_VERSION,
                "framework": "ultralytics",
                "framework_version": self.estimator.framework_version,
                "torch_version": self.estimator.torch_version,
                "cuda_version": self.estimator.cuda_version,
                "device": self.estimator.device,
                "gpu_name": self.estimator.gpu_name,
                "gpu_memory_total_mib": _rounded(self.estimator.gpu_memory_total_mib),
                "gpu_memory_allocated_mib": _rounded(
                    self.estimator.gpu_memory_allocated_mib()
                ),
                "model_load_ms": _rounded(self.estimator.model_load_ms),
                "model_checksum": self.estimator.model_checksum,
                "input_size": self.settings.fall_config.input_size,
                "source_fps": _rounded(self.source_fps),
                "sample_fps": _rounded(self.sampled_fps),
                "inference_fps": _rounded(self.estimator.inference_fps),
                "reconnect_count": self.reader.reconnect_count,
                "last_result_at": self.last_result_at.isoformat() if self.last_result_at else None,
                "error": self.last_error,
            }
        }

    async def _run(self) -> None:
        try:
            await asyncio.to_thread(self.estimator.load)
        except PoseModelError:
            self.capability = "unavailable"
            self.detector_status = "model_unavailable"
            self.last_error = "Pose model could not be loaded"
            logger.error("Fall detection unavailable: pose model load failed")
            return

        self.capability = "installed"
        self.detector_status = "waiting_for_media"
        while True:
            try:
                self.device = await self.media_client.select_device()
                self.last_error = None
                await self._consume_device(self.device)
            except asyncio.CancelledError:
                raise
            except MediaBackendError:
                self.capability = "unavailable"
                self.detector_status = "media_unavailable"
                self.last_error = "No usable camera stream is currently available"
                logger.warning("Fall detection waiting for an online media device")
                await asyncio.sleep(self.settings.media_reconnect_seconds)
            except PoseModelError:
                self.capability = "error"
                self.detector_status = "inference_error"
                self.last_error = "Pose inference failed"
                logger.error("Fall detection pose inference failed")
                await asyncio.sleep(self.settings.media_reconnect_seconds)
            except Exception:
                self.capability = "error"
                self.detector_status = "runtime_error"
                self.last_error = "Fall detection runtime failed"
                logger.error("Fall detection runtime failed; details suppressed")
                await asyncio.sleep(self.settings.media_reconnect_seconds)

    async def _consume_device(self, device: MediaDevice) -> None:
        async for frame in self.reader.frames(device.serial):
            self.source_fps = frame.source_fps
            if not self.sampler.should_sample(frame.media_seconds):
                continue
            self._record_sample(frame.arrival_monotonic_seconds)
            pose_frame = await asyncio.to_thread(self.estimator.infer, frame)
            self.capability = "running"
            self.detector_status = "running"
            person = pose_frame.primary_person
            if (
                person is None
                or person.mean_keypoint_confidence
                < self.settings.fall_config.minimum_keypoint_confidence
            ):
                self.extractor.reset()
                await self._maybe_publish_no_person(device, frame)
                continue

            detector_started = time.perf_counter()
            features = self.extractor.extract(person, frame.media_seconds)
            if features is None:
                await self._maybe_publish_no_person(device, frame, label="low_pose_confidence")
                continue
            decision = self.detector.update(features, frame.media_seconds)
            detector_ms = (time.perf_counter() - detector_started) * 1000
            if self.policy.should_publish(decision, frame.media_seconds):
                await self._publish_decision(
                    device,
                    frame.captured_at,
                    person.person_id,
                    decision,
                    pose_frame.inference_ms,
                    detector_ms,
                )

    async def _publish_decision(
        self,
        device: MediaDevice,
        source_timestamp: datetime,
        person_id: str,
        decision: FallDecision,
        inference_ms: float,
        detector_ms: float,
    ) -> None:
        level = {
            FallState.NORMAL: RiskLevel.NORMAL,
            FallState.SUSPECTED_FALL: RiskLevel.HIGH,
            FallState.FALLEN: RiskLevel.CRITICAL,
            FallState.RECOVERING: RiskLevel.MEDIUM,
        }[decision.state]
        features = decision.features
        result = self._result(
            device=device,
            source_timestamp=source_timestamp,
            label=decision.state.value,
            score=decision.score,
            level=level,
            latency_ms=inference_ms + detector_ms,
            metadata={
                "detector_status": "running",
                "detector_state": decision.state.value,
                "score_type": "heuristic",
                "person_detected": True,
                "person_id": person_id,
                "keypoint_confidence": round(features.keypoint_confidence, 4),
                "torso_angle_degrees": round(features.torso_angle_degrees, 3),
                "hip_vertical_velocity": round(features.hip_vertical_velocity, 4),
                "body_vertical_velocity": round(features.body_center_vertical_velocity, 4),
                "bbox_aspect_ratio": round(features.bbox_aspect_ratio, 4),
                "source_fps": _rounded(self.source_fps),
                "sample_fps": _rounded(self.sampled_fps),
                "inference_fps": _rounded(self.estimator.inference_fps),
                "pose_inference_ms": round(inference_ms, 3),
                "detector_latency_ms": round(detector_ms, 3),
                "publish_rate_hz": _rounded(self.publish_rate),
                "ai_device": self.estimator.device,
                "gpu_name": self.estimator.gpu_name,
                "model_name": self.settings.fall_model_name,
                "input_size": self.settings.fall_config.input_size,
            },
        )
        await self._safe_publish(result)

    async def _maybe_publish_no_person(
        self,
        device: MediaDevice,
        frame,
        *,
        label: str = "no_person",
    ) -> None:
        if frame.media_seconds - self._last_empty_publish < self.settings.fall_config.result_heartbeat_seconds:
            return
        self._last_empty_publish = frame.media_seconds
        result = self._result(
            device=device,
            source_timestamp=frame.captured_at,
            label=label,
            score=None,
            level=None,
            latency_ms=self.estimator.last_inference_ms,
            metadata={
                "detector_status": label,
                "detector_state": self.detector.state.value,
                "score_type": "heuristic",
                "person_detected": False,
                "keypoint_confidence": None,
                "source_fps": _rounded(self.source_fps),
                "sample_fps": _rounded(self.sampled_fps),
                "inference_fps": _rounded(self.estimator.inference_fps),
                "pose_inference_ms": _rounded(self.estimator.last_inference_ms),
                "ai_device": self.estimator.device,
                "gpu_name": self.estimator.gpu_name,
                "model_name": self.settings.fall_model_name,
                "input_size": self.settings.fall_config.input_size,
            },
        )
        await self._safe_publish(result)

    def _result(
        self,
        *,
        device: MediaDevice,
        source_timestamp: datetime,
        label: str,
        score: float | None,
        level: RiskLevel | None,
        latency_ms: float | None,
        metadata: dict,
    ) -> AlgorithmResult:
        return AlgorithmResult(
            result_id=uuid4(),
            task=AlgorithmTask.FALL_DETECTION,
            model_id=self.MODEL_ID,
            model_version=self.MODEL_VERSION,
            device_id=device.id,
            source_timestamp=source_timestamp,
            result_timestamp=datetime.now(timezone.utc),
            label=label,
            score=score,
            level=level,
            latency_ms=latency_ms,
            metadata=metadata,
            simulated=False,
        )

    async def _safe_publish(self, result: AlgorithmResult) -> None:
        try:
            await self.publisher.publish(result)
        except PublishError:
            logger.warning("Fall detection result delivery failed; monitoring continues")
            return
        self.last_result_at = result.result_timestamp
        self._publish_count += 1
        self._update_rates(time.monotonic())

    def _record_sample(self, timestamp_seconds: float) -> None:
        if self._metrics_started_at is None:
            self._metrics_started_at = timestamp_seconds
        self._sample_count += 1
        self._update_rates(timestamp_seconds)

    def _update_rates(self, now: float) -> None:
        if self._metrics_started_at is None:
            return
        elapsed = now - self._metrics_started_at
        if elapsed > 0:
            self.sampled_fps = self._sample_count / elapsed
            self.publish_rate = self._publish_count / elapsed

    def _set_stream_status(self, status: str) -> None:
        self.stream_status = status
        if status == "reconnecting":
            self.sampler.reset()
            self.extractor.reset()
            self.detector.reset()
            self.policy.reset()
            self._last_empty_publish = 0.0
            self.capability = "unavailable"
            self.detector_status = "media_reconnecting"
            self.last_error = "Camera stream is reconnecting"
        elif status == "connected":
            if self.capability == "unavailable":
                self.capability = "installed"
            self.detector_status = "waiting_for_pose"
            self.last_error = None


def _rounded(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None
