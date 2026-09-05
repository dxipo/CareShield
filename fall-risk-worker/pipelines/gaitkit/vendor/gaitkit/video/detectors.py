"""Optional person detectors.

The default motion backend needs no model weights.  YOLO is optional and is
loaded only when the user supplies ``--yolo-model``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from .segmentation import BBox


class YoloPersonDetector:
    def __init__(self, model_path: Path, confidence: float = 0.35) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "YOLO模式需要安装ultralytics；也可以不指定--yolo-model，使用内置motion模式。"
            ) from exc
        self.model = YOLO(str(model_path))
        self.confidence = float(confidence)

    def __call__(self, frame: np.ndarray) -> Optional[BBox]:
        result = self.model.predict(frame, conf=self.confidence, verbose=False)[0]
        if result.boxes is None or len(result.boxes) == 0:
            return None
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        confidences = result.boxes.conf.detach().cpu().numpy()
        classes = result.boxes.cls.detach().cpu().numpy()
        candidates = [
            (float(conf), box)
            for box, conf, cls in zip(boxes, confidences, classes)
            if int(cls) == 0
        ]
        if not candidates:
            return None
        _, box = max(candidates, key=lambda item: item[0])
        x1, y1, x2, y2 = [int(round(v)) for v in box]
        return x1, y1, max(1, x2 - x1), max(1, y2 - y1)
