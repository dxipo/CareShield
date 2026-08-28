from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from app.core.config import WorkerSettings
from app.fall_detection.pose import (
    BoundingBox,
    PersonDetection,
    PersonDetectionFrame,
)
from app.fall_detection.pose_estimator import PoseModelError
from app.media.reader import DecodedFrame


class UltralyticsPersonDetector:
    """Independent COCO person detector used when pose keypoints disappear."""

    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings
        self.model: Any = None
        self.model_checksum = "unavailable"
        self.model_load_ms: float | None = None
        self.last_inference_ms: float | None = None

    def load(self, device: str) -> None:
        try:
            from ultralytics import YOLO

            started = time.perf_counter()
            model_path = Path(self.settings.fall_person_model_path)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            self.model = YOLO(str(model_path))
            self.model.to(device)
            if model_path.is_file():
                self.model_checksum = _sha256(model_path)
            self.model_load_ms = (time.perf_counter() - started) * 1000
        except Exception as exc:
            raise PoseModelError("Person detection model could not be loaded") from exc

    def infer(self, frame: DecodedFrame, device: str) -> PersonDetectionFrame:
        if self.model is None:
            raise PoseModelError("Person detection model is not loaded")
        try:
            import torch

            if device.startswith("cuda"):
                torch.cuda.synchronize()
            started = time.perf_counter()
            result = self.model.predict(
                source=frame.image,
                imgsz=self.settings.fall_config.input_size,
                conf=self.settings.person_confidence,
                classes=[0],
                device=device,
                verbose=False,
            )[0]
            if device.startswith("cuda"):
                torch.cuda.synchronize()
            self.last_inference_ms = (time.perf_counter() - started) * 1000
            return PersonDetectionFrame(
                timestamp=frame.captured_at,
                detections=self._normalize(
                    result,
                    frame.source_width,
                    frame.source_height,
                ),
                inference_ms=self.last_inference_ms,
            )
        except Exception as exc:
            raise PoseModelError("Person detection inference failed") from exc

    @staticmethod
    def _normalize(result: Any, width: int, height: int) -> tuple[PersonDetection, ...]:
        if result.boxes is None:
            return ()
        boxes = result.boxes.xyxy.detach().cpu().tolist()
        confidences = result.boxes.conf.detach().cpu().tolist()
        safe_width, safe_height = max(width, 1), max(height, 1)
        return tuple(
            PersonDetection(
                bbox=BoundingBox(
                    x1=_unit(float(box[0]) / safe_width),
                    y1=_unit(float(box[1]) / safe_height),
                    x2=_unit(float(box[2]) / safe_width),
                    y2=_unit(float(box[3]) / safe_height),
                ),
                confidence=_unit(float(confidence)),
            )
            for box, confidence in zip(boxes, confidences)
        )


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
