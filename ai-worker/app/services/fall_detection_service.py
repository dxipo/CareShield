from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from careshield_contracts import AlgorithmResult, AlgorithmTask, RiskLevel

from app.core.config import WorkerSettings
from app.fall_detection.alert import FallAlertLatch
from app.fall_detection.detector import FallState
from app.fall_detection.fusion import fuse_person_detections
from app.fall_detection.person_detector import UltralyticsPersonDetector
from app.fall_detection.pose import PosePerson, pose_is_reliable
from app.fall_detection.pose_estimator import PoseModelError, UltralyticsPoseEstimator
from app.fall_detection.preview import AnnotatedPreview, render_preview
from app.fall_detection.publish_policy import FallPublishPolicy
from app.fall_detection.sequence import PoseSequenceStore
from app.fall_detection.stgcn_classifier import (
    STGCNClassifier,
    STGCNModelError,
    STGCNPrediction,
)
from app.fall_detection.stgcn_decision import STGCNDecision, STGCNDecisionEngine
from app.fall_detection.tracking import IoUPersonTracker
from app.media.backend_client import BackendMediaClient, MediaBackendError, MediaDevice
from app.media.frame_sampler import FrameSampler
from app.media.reader import MediaReader
from app.publisher.result_publisher import PublishError, ResultPublisher


logger = logging.getLogger(__name__)


class FallDetectionService:
    MODEL_ID = "stgcn-extend-fall-classifier"
    MODEL_VERSION = "real440-m5.2-v1"

    def __init__(
        self,
        settings: WorkerSettings,
        publisher: ResultPublisher,
        media_client: BackendMediaClient,
        *,
        estimator: UltralyticsPoseEstimator | None = None,
        person_detector: UltralyticsPersonDetector | None = None,
        classifier: STGCNClassifier | None = None,
        preview: AnnotatedPreview | None = None,
    ) -> None:
        config = settings.fall_config
        self.settings = settings
        self.publisher = publisher
        self.media_client = media_client
        self.estimator = estimator or UltralyticsPoseEstimator(settings)
        self.person_detector = person_detector or UltralyticsPersonDetector(settings)
        self.classifier = classifier
        self.preview = preview or AnnotatedPreview()
        self.tracker = IoUPersonTracker(
            config.tracking_minimum_iou,
            config.tracking_maximum_missing_frames,
            config.tracking_maximum_center_distance,
        )
        self.sequences = PoseSequenceStore(
            observed_length=config.observed_sequence_length,
            model_length=config.sequence_length,
            window_seconds=config.observation_window_seconds,
            minimum_confidence=config.minimum_keypoint_confidence,
        )
        self.decision = STGCNDecisionEngine(
            config.stgcn_suspected_threshold,
            config.stgcn_fallen_threshold,
            config.stgcn_confirmation_windows,
            config.stgcn_recovery_windows,
        )
        self.sampler = FrameSampler(config.input_fps)
        self.policy = FallPublishPolicy(
            config.result_heartbeat_seconds,
            config.significant_score_delta,
        )
        self.alert = FallAlertLatch(config.alert_minimum_visible_seconds)
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
        self.processing_fps: float | None = None
        self.publish_rate: float | None = None
        self.person_count = 0
        self.detection_count = 0
        self.pose_count = 0
        self.fused_count = 0
        self.pose_crop_fallback_used = False
        self.sequence_progress = 0.0
        self.last_fall_score: float | None = None
        self._task: asyncio.Task | None = None
        self._sample_count = 0
        self._publish_count = 0
        self._metrics_started_at: float | None = None
        self._first_sample_media_seconds: float | None = None
        self._last_empty_publish = 0.0
        self._last_classifier_at: float | None = None
        self._primary_tracker_id: str | None = None

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
        classifier = self.classifier
        return {
            "fall_detection": {
                "status": self.detector_status,
                "stream_status": self.stream_status,
                "device_id": self.device.id if self.device else None,
                "device_model": self.device.model if self.device else None,
                "model": self.settings.fall_classifier_model_name,
                "model_version": self.MODEL_VERSION,
                "model_type": "STGCN-Extend binary classifier",
                "model_checksum": classifier.model_checksum if classifier else "unavailable",
                "classifier_load_ms": _rounded(classifier.model_load_ms if classifier else None),
                "classifier_inference_ms": _rounded(
                    classifier.last_inference_ms if classifier else None
                ),
                "pose_model": self.settings.fall_model_name,
                "person_model": self.settings.fall_person_model_name,
                "person_model_checksum": self.person_detector.model_checksum,
                "person_model_load_ms": _rounded(self.person_detector.model_load_ms),
                "person_inference_ms": _rounded(self.person_detector.last_inference_ms),
                "pose_model_checksum": self.estimator.model_checksum,
                "framework": "pytorch + ultralytics",
                "framework_version": self.estimator.framework_version,
                "torch_version": self.estimator.torch_version,
                "cuda_version": self.estimator.cuda_version,
                "device": self.estimator.device,
                "gpu_name": self.estimator.gpu_name,
                "gpu_memory_total_mib": _rounded(self.estimator.gpu_memory_total_mib),
                "gpu_memory_allocated_mib": _rounded(
                    self.estimator.gpu_memory_allocated_mib()
                ),
                "pose_model_load_ms": _rounded(self.estimator.model_load_ms),
                "input_size": self.settings.fall_config.input_size,
                "pose_confidence": self.settings.pose_confidence,
                "person_confidence": self.settings.person_confidence,
                "sequence_length": self.settings.fall_config.sequence_length,
                "observed_sequence_length": self.settings.fall_config.observed_sequence_length,
                "predicted_sequence_length": (
                    self.settings.fall_config.sequence_length
                    - self.settings.fall_config.observed_sequence_length
                ),
                "observation_window_seconds": self.settings.fall_config.observation_window_seconds,
                "sequence_resampling": "linear_interpolation",
                "sequence_progress": round(self.sequence_progress, 3),
                "last_fall_score": _rounded(self.last_fall_score),
                "person_count": self.person_count,
                "detection_count": self.detection_count,
                "pose_count": self.pose_count,
                "fused_count": self.fused_count,
                "pose_crop_fallback_used": self.pose_crop_fallback_used,
                "pose_crop_rotation": self.estimator.last_region_rotation,
                "alert_active": self.alert.active,
                "alert_acknowledged": self.alert.acknowledged,
                "source_fps": _rounded(self.source_fps),
                "sample_fps": _rounded(self.sampled_fps),
                "processing_fps": _rounded(self.processing_fps),
                "pose_inference_fps": _rounded(self.estimator.inference_fps),
                "classifier_inference_hz": self.settings.fall_config.classifier_inference_hz,
                "reconnect_count": self.reader.reconnect_count,
                "last_disconnect_reason": self.reader.last_disconnect_reason,
                "last_session_frames": self.reader.last_session_frames,
                "last_session_seconds": _rounded(self.reader.last_session_seconds),
                "last_result_at": self.last_result_at.isoformat() if self.last_result_at else None,
                "error": self.last_error,
            }
        }

    async def _run(self) -> None:
        try:
            await asyncio.to_thread(self.estimator.load)
            await asyncio.to_thread(self.person_detector.load, self.estimator.device)
            if self.classifier is None:
                self.classifier = STGCNClassifier(
                    self.settings.fall_classifier_model_path,
                    self.estimator.device,
                )
            await asyncio.to_thread(self.classifier.load)
        except PoseModelError:
            self._mark_model_unavailable("Pose model could not be loaded")
            return
        except STGCNModelError:
            self._mark_model_unavailable("STGCN classifier could not be loaded")
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
            except (PoseModelError, STGCNModelError):
                self.capability = "error"
                self.detector_status = "inference_error"
                self.last_error = "Fall model inference failed"
                logger.error("Fall detection model inference failed")
                await asyncio.sleep(self.settings.media_reconnect_seconds)
            except Exception:
                self.capability = "error"
                self.detector_status = "runtime_error"
                self.last_error = "Fall detection runtime failed"
                logger.exception("Fall detection runtime failed")
                await asyncio.sleep(self.settings.media_reconnect_seconds)

    async def _consume_device(self, device: MediaDevice) -> None:
        async for frame in self.reader.frames(device.serial):
            self.source_fps = frame.source_fps
            if not self.sampler.should_sample(frame.media_seconds):
                continue
            self._record_sample(
                frame.media_seconds,
                frame.arrival_monotonic_seconds,
            )
            # Two small models run sequentially on the same CUDA device. Their
            # combined latency remains below a 15 FPS frame budget and avoids
            # competing PyTorch/Ultralytics calls from separate host threads.
            detection_frame = await asyncio.to_thread(
                self.person_detector.infer,
                frame,
                self.estimator.device,
            )
            self.estimator.last_region_rotation = "none"
            pose_frame = await asyncio.to_thread(self.estimator.infer, frame)
            self.pose_crop_fallback_used = False
            if not pose_frame.persons and detection_frame.detections:
                primary_detection = max(
                    detection_frame.detections,
                    key=lambda detection: (
                        detection.confidence,
                        detection.bbox.width * detection.bbox.height,
                    ),
                )
                pose_frame = await asyncio.to_thread(
                    self.estimator.infer_region,
                    frame,
                    primary_detection.bbox,
                )
                self.pose_crop_fallback_used = bool(pose_frame.persons)
            fused_persons = fuse_person_detections(
                detection_frame.detections,
                pose_frame.persons,
            )
            self.detection_count = len(detection_frame.detections)
            self.pose_count = len(pose_frame.persons)
            self.fused_count = len(fused_persons)
            tracked_persons = self.tracker.update(fused_persons)
            persons = self._select_primary_person(tracked_persons)
            self.person_count = len(persons)
            self.sequences.update(
                persons,
                ("primary-person",) if persons else (),
                frame.media_seconds,
            )
            self.capability = "running"

            if not persons:
                self.detector_status = "no_person"
                self.sequence_progress = 0.0
                await self._update_preview(frame.image, persons)
                await self._maybe_publish_status(device, frame, "no_person")
                continue

            reliable_persons = tuple(
                person
                for person in persons
                if pose_is_reliable(
                    person,
                    self.settings.fall_config.minimum_keypoint_confidence,
                )
            )
            if not reliable_persons:
                self.detector_status = "low_pose_confidence"
                self.sequence_progress = 0.0
                await self._update_preview(frame.image, persons)
                await self._maybe_publish_status(
                    device,
                    frame,
                    "low_pose_confidence",
                    person_detected=True,
                )
                continue

            self.sequence_progress = max(
                self.sequences.progress(person.person_id) for person in reliable_persons
            )
            if not any(
                self.sequences.ready(person.person_id) for person in reliable_persons
            ):
                self.detector_status = "warming_up"
                await self._update_preview(frame.image, persons)
                await self._maybe_publish_status(
                    device,
                    frame,
                    "warming_up",
                    person_detected=True,
                )
                continue

            sequence_persons = tuple(
                person
                for person in reliable_persons
                if self.sequences.valid_ratio(person.person_id)
                >= self.settings.fall_config.minimum_sequence_valid_ratio
            )
            if not sequence_persons:
                self.detector_status = "low_pose_confidence"
                await self._update_preview(frame.image, persons)
                await self._maybe_publish_status(
                    device,
                    frame,
                    "low_pose_confidence",
                    person_detected=True,
                )
                continue

            if not self._classifier_due(frame.media_seconds):
                await self._update_preview(frame.image, persons)
                continue

            prediction, person_id = await self._classify_persons(sequence_persons)
            self.last_fall_score = prediction.fall_score
            decision = self.decision.update(prediction.fall_score)
            self.alert.update(decision.state)
            self.detector_status = decision.state.value
            await self._update_preview(frame.image, persons)
            if self.policy.should_publish(decision, frame.media_seconds):
                await self._publish_decision(
                    device,
                    frame.captured_at,
                    person_id,
                    sequence_persons,
                    decision,
                    detection_frame.inference_ms,
                    pose_frame.inference_ms,
                    prediction.latency_ms,
                )

    async def _classify_persons(
        self,
        persons,
    ) -> tuple[STGCNPrediction, str]:
        if self.classifier is None:
            raise STGCNModelError("STGCN classifier is unavailable")
        predictions: list[tuple[STGCNPrediction, str]] = []
        for person in persons:
            if not self.sequences.ready(person.person_id):
                continue
            prediction = await asyncio.to_thread(
                self.classifier.infer,
                self.sequences.tensor(person.person_id),
            )
            predictions.append((prediction, person.person_id))
        if not predictions:
            raise STGCNModelError("No complete pose sequence is available")
        return max(predictions, key=lambda item: item[0].fall_score)

    async def _publish_decision(
        self,
        device: MediaDevice,
        source_timestamp: datetime,
        person_id: str,
        persons,
        decision: STGCNDecision,
        person_inference_ms: float,
        pose_inference_ms: float,
        classifier_inference_ms: float,
    ) -> None:
        level = {
            FallState.NORMAL: RiskLevel.NORMAL,
            FallState.SUSPECTED_FALL: RiskLevel.HIGH,
            FallState.FALLEN: RiskLevel.CRITICAL,
            FallState.RECOVERING: RiskLevel.MEDIUM,
        }[decision.state]
        selected = next(person for person in persons if person.person_id == person_id)
        result = self._result(
            device=device,
            source_timestamp=source_timestamp,
            label=decision.state.value,
            score=decision.score,
            level=level,
            latency_ms=person_inference_ms + pose_inference_ms + classifier_inference_ms,
            metadata={
                "detector_status": "running",
                "detector_state": decision.state.value,
                "score_type": "stgcn_softmax_uncalibrated",
                "person_detected": True,
                "person_count": len(persons),
                "detection_count": self.detection_count,
                "pose_count": self.pose_count,
                "fused_count": self.fused_count,
                "pose_crop_fallback_used": self.pose_crop_fallback_used,
                "pose_crop_rotation": self.estimator.last_region_rotation,
                "person_id": person_id,
                "alert_active": self.alert.active,
                "alert_acknowledged": self.alert.acknowledged,
                "keypoint_confidence": round(selected.mean_keypoint_confidence, 4),
                "source_fps": _rounded(self.source_fps),
                "sample_fps": _rounded(self.sampled_fps),
                "processing_fps": _rounded(self.processing_fps),
                "pose_inference_fps": _rounded(self.estimator.inference_fps),
                "pose_inference_ms": round(pose_inference_ms, 3),
                "person_inference_ms": round(person_inference_ms, 3),
                "classifier_inference_ms": round(classifier_inference_ms, 3),
                "publish_rate_hz": _rounded(self.publish_rate),
                "ai_device": self.estimator.device,
                "gpu_name": self.estimator.gpu_name,
                "pose_model_name": self.settings.fall_model_name,
                "person_model_name": self.settings.fall_person_model_name,
                "classifier_model_name": self.settings.fall_classifier_model_name,
                "sequence_length": self.settings.fall_config.sequence_length,
                "observed_sequence_length": self.settings.fall_config.observed_sequence_length,
                "predicted_sequence_length": (
                    self.settings.fall_config.sequence_length
                    - self.settings.fall_config.observed_sequence_length
                ),
                "observation_window_seconds": self.settings.fall_config.observation_window_seconds,
                "sequence_resampling": "linear_interpolation",
                "sequence_progress": 1.0,
                "sequence_valid_ratio": round(
                    self.sequences.valid_ratio(person_id),
                    3,
                ),
                "input_size": self.settings.fall_config.input_size,
            },
        )
        await self._safe_publish(result)

    async def _maybe_publish_status(
        self,
        device: MediaDevice,
        frame,
        label: str,
        *,
        person_detected: bool = False,
    ) -> None:
        if (
            frame.media_seconds - self._last_empty_publish
            < self.settings.fall_config.result_heartbeat_seconds
        ):
            return
        self._last_empty_publish = frame.media_seconds
        result = self._result(
            device=device,
            source_timestamp=frame.captured_at,
            label=label,
            score=None,
            level=None,
            latency_ms=_sum_optional(
                self.person_detector.last_inference_ms,
                self.estimator.last_inference_ms,
            ),
            metadata={
                "detector_status": label,
                "detector_state": self.decision.state.value,
                "score_type": "stgcn_softmax_uncalibrated",
                "person_detected": person_detected,
                "person_count": self.person_count,
                "detection_count": self.detection_count,
                "pose_count": self.pose_count,
                "fused_count": self.fused_count,
                "pose_crop_fallback_used": self.pose_crop_fallback_used,
                "pose_crop_rotation": self.estimator.last_region_rotation,
                "alert_active": self.alert.active,
                "alert_acknowledged": self.alert.acknowledged,
                "keypoint_confidence": None,
                "sequence_length": self.settings.fall_config.sequence_length,
                "observed_sequence_length": self.settings.fall_config.observed_sequence_length,
                "predicted_sequence_length": (
                    self.settings.fall_config.sequence_length
                    - self.settings.fall_config.observed_sequence_length
                ),
                "observation_window_seconds": self.settings.fall_config.observation_window_seconds,
                "sequence_resampling": "linear_interpolation",
                "sequence_progress": round(self.sequence_progress, 3),
                "last_fall_score": _rounded(self.last_fall_score),
                "source_fps": _rounded(self.source_fps),
                "sample_fps": _rounded(self.sampled_fps),
                "processing_fps": _rounded(self.processing_fps),
                "pose_inference_fps": _rounded(self.estimator.inference_fps),
                "pose_inference_ms": _rounded(self.estimator.last_inference_ms),
                "person_inference_ms": _rounded(self.person_detector.last_inference_ms),
                "ai_device": self.estimator.device,
                "gpu_name": self.estimator.gpu_name,
                "pose_model_name": self.settings.fall_model_name,
                "person_model_name": self.settings.fall_person_model_name,
                "classifier_model_name": self.settings.fall_classifier_model_name,
            },
        )
        await self._safe_publish(result)

    async def _update_preview(self, image, persons) -> None:
        try:
            jpeg = await asyncio.to_thread(
                render_preview,
                image,
                persons,
                self.alert.active,
                minimum_confidence=self.settings.fall_config.minimum_keypoint_confidence,
            )
            await self.preview.update(jpeg)
        except Exception:
            logger.warning("Annotated fall preview could not be updated")

    def _classifier_due(self, media_seconds: float) -> bool:
        interval = 1.0 / self.settings.fall_config.classifier_inference_hz
        if self._last_classifier_at is None or media_seconds - self._last_classifier_at >= interval:
            self._last_classifier_at = media_seconds
            return True
        return False

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
        self._update_wall_rates(time.monotonic())

    def _record_sample(
        self,
        media_seconds: float,
        arrival_seconds: float,
    ) -> None:
        if self._metrics_started_at is None:
            self._metrics_started_at = arrival_seconds
        if self._first_sample_media_seconds is None:
            self._first_sample_media_seconds = media_seconds
        self._sample_count += 1
        wall_elapsed = arrival_seconds - self._metrics_started_at
        if wall_elapsed > 0 and self._sample_count > 1:
            self.sampled_fps = (self._sample_count - 1) / wall_elapsed
        self._update_wall_rates(arrival_seconds)

    def _update_wall_rates(self, now: float) -> None:
        if self._metrics_started_at is None:
            return
        elapsed = now - self._metrics_started_at
        if elapsed > 0:
            self.processing_fps = self._sample_count / elapsed
            self.publish_rate = self._publish_count / elapsed

    def _set_stream_status(self, status: str) -> None:
        self.stream_status = status
        if status == "reconnecting":
            self.sampler.reset()
            self.tracker.reset()
            self.sequences.reset()
            self.decision.reset()
            self.policy.reset()
            self._last_empty_publish = 0.0
            self._last_classifier_at = None
            self._sample_count = 0
            self._publish_count = 0
            self._metrics_started_at = None
            self._first_sample_media_seconds = None
            self.sampled_fps = None
            self.processing_fps = None
            self.publish_rate = None
            self._primary_tracker_id = None
            self.capability = "unavailable"
            self.detector_status = "media_reconnecting"
            self.last_error = "Camera stream is reconnecting"
        elif status == "connected":
            if self.capability == "unavailable":
                self.capability = "installed"
            self.detector_status = "waiting_for_pose"
            self.last_error = None

    def _mark_model_unavailable(self, message: str) -> None:
        self.capability = "unavailable"
        self.detector_status = "model_unavailable"
        self.last_error = message
        logger.error("Fall detection unavailable: %s", message)

    def acknowledge_alert(self) -> dict[str, bool]:
        self.alert.acknowledge()
        return {
            "alert_active": self.alert.active,
            "alert_acknowledged": self.alert.acknowledged,
        }

    def _select_primary_person(
        self,
        persons: tuple[PosePerson, ...],
    ) -> tuple[PosePerson, ...]:
        """Expose one stable analysis subject for the current home baseline.

        The tracker still maintains all detected people. M5's classifier and
        preview intentionally follow one primary subject so transient secondary
        detections cannot reset or contaminate its temporal sequence.
        """
        if not persons:
            return ()
        selected = next(
            (
                person
                for person in persons
                if person.person_id == self._primary_tracker_id
            ),
            None,
        )
        if selected is None:
            selected = max(
                persons,
                key=lambda person: (
                    pose_is_reliable(
                        person,
                        self.settings.fall_config.minimum_keypoint_confidence,
                    ),
                    person.mean_keypoint_confidence,
                    person.bbox.width * person.bbox.height,
                    person.bbox_confidence,
                ),
            )
            self._primary_tracker_id = selected.person_id
        return (replace(selected, person_id="primary-person"),)


def _rounded(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _sum_optional(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None
