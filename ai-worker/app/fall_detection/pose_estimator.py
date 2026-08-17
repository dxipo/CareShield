from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from app.core.config import WorkerSettings
from app.fall_detection.pose import BoundingBox, PoseFrame, PoseKeypoint, PosePerson
from app.media.reader import DecodedFrame


COCO_KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


class PoseModelError(RuntimeError):
    """Model failure with no stream address or credential context."""


class UltralyticsPoseEstimator:
    """Isolate Ultralytics objects behind the stable CareShield pose schema."""

    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings
        self.model: Any = None
        self.device = "unavailable"
        self.framework_version = "unavailable"
        self.torch_version = "unavailable"
        self.cuda_version = "unavailable"
        self.gpu_name = "unavailable"
        self.gpu_memory_total_mib: float | None = None
        self.model_checksum = "unavailable"
        self.model_load_ms: float | None = None
        self.last_inference_ms: float | None = None
        self._inference_count = 0
        self._inference_total_seconds = 0.0

    def load(self) -> None:
        started = time.perf_counter()
        try:
            Path(os.getenv("YOLO_CONFIG_DIR", "/models/ultralytics-config")).mkdir(
                parents=True,
                exist_ok=True,
            )
            Path(os.getenv("TORCH_HOME", "/models/torch-cache")).mkdir(
                parents=True,
                exist_ok=True,
            )
            import torch
            import ultralytics
            from ultralytics import YOLO

            self.torch_version = torch.__version__
            self.cuda_version = torch.version.cuda or "unavailable"
            self.framework_version = ultralytics.__version__
            self.device = self._resolve_device(torch)
            if self.device.startswith("cuda"):
                index = int(self.device.partition(":")[2] or 0)
                properties = torch.cuda.get_device_properties(index)
                self.gpu_name = properties.name
                self.gpu_memory_total_mib = properties.total_memory / 1024 / 1024

            model_path = Path(self.settings.fall_model_path)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            self.model = YOLO(str(model_path))
            self.model.to(self.device)
            if model_path.is_file():
                self.model_checksum = _sha256(model_path)
            self.model_load_ms = (time.perf_counter() - started) * 1000
        except Exception as exc:
            raise PoseModelError("Pose model could not be loaded") from exc

    def infer(self, frame: DecodedFrame) -> PoseFrame:
        if self.model is None:
            raise PoseModelError("Pose model is not loaded")
        try:
            import torch

            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            started = time.perf_counter()
            results = self.model.predict(
                source=frame.image,
                imgsz=self.settings.fall_config.input_size,
                conf=self.settings.pose_confidence,
                device=self.device,
                verbose=False,
            )
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            inference_seconds = time.perf_counter() - started
            self.last_inference_ms = inference_seconds * 1000
            self._inference_count += 1
            self._inference_total_seconds += inference_seconds
            persons = self._normalize(results[0], frame.source_width, frame.source_height)
            return PoseFrame(
                timestamp=frame.captured_at,
                source_width=frame.source_width,
                source_height=frame.source_height,
                persons=persons,
                inference_ms=self.last_inference_ms,
            )
        except PoseModelError:
            raise
        except Exception as exc:
            raise PoseModelError("Pose inference failed") from exc

    @property
    def inference_fps(self) -> float | None:
        if self._inference_total_seconds <= 0:
            return None
        return self._inference_count / self._inference_total_seconds

    def gpu_memory_allocated_mib(self) -> float | None:
        if not self.device.startswith("cuda"):
            return None
        try:
            import torch

            return torch.cuda.memory_allocated() / 1024 / 1024
        except Exception:
            return None

    def _resolve_device(self, torch: Any) -> str:
        requested = self.settings.ai_device
        if requested == "auto":
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        if requested == "cuda":
            requested = "cuda:0"
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise PoseModelError("CUDA was requested but is unavailable")
        if requested != "cpu" and not requested.startswith("cuda"):
            raise PoseModelError("AI_DEVICE must be auto, cpu, cuda, or cuda:<index>")
        return requested

    @staticmethod
    def _normalize(result: Any, width: int, height: int) -> tuple[PosePerson, ...]:
        if result.boxes is None or result.keypoints is None:
            return ()
        boxes = result.boxes.xyxy.detach().cpu().tolist()
        box_confidences = result.boxes.conf.detach().cpu().tolist()
        normalized_points = result.keypoints.xyn.detach().cpu().tolist()
        point_confidences = (
            result.keypoints.conf.detach().cpu().tolist()
            if result.keypoints.conf is not None
            else [[1.0] * len(COCO_KEYPOINT_NAMES) for _ in normalized_points]
        )

        persons: list[PosePerson] = []
        safe_width, safe_height = max(width, 1), max(height, 1)
        for index, (box, confidence, points, confidences) in enumerate(
            zip(boxes, box_confidences, normalized_points, point_confidences),
            start=1,
        ):
            keypoints = tuple(
                PoseKeypoint(
                    name=name,
                    x=_unit(float(point[0])),
                    y=_unit(float(point[1])),
                    confidence=_unit(float(point_confidence)),
                )
                for name, point, point_confidence in zip(
                    COCO_KEYPOINT_NAMES,
                    points,
                    confidences,
                )
            )
            persons.append(
                PosePerson(
                    person_id=f"person-{index}",
                    bbox=BoundingBox(
                        x1=_unit(float(box[0]) / safe_width),
                        y1=_unit(float(box[1]) / safe_height),
                        x2=_unit(float(box[2]) / safe_width),
                        y2=_unit(float(box[3]) / safe_height),
                    ),
                    bbox_confidence=_unit(float(confidence)),
                    keypoints=keypoints,
                )
            )
        return tuple(persons)


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
