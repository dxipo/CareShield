from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.fall_detection.stgcn_extend import STGCNExtend


class STGCNModelError(RuntimeError):
    """Classifier failure without checkpoint contents or media credentials."""


@dataclass(frozen=True, slots=True)
class STGCNPrediction:
    fall_score: float
    label_index: int
    latency_ms: float


class STGCNClassifier:
    def __init__(self, model_path: str, device: str) -> None:
        self.model_path = Path(model_path)
        self.device = device
        self.model = None
        self.model_checksum = "unavailable"
        self.model_load_ms: float | None = None
        self.last_inference_ms: float | None = None

    def load(self) -> None:
        if not self.model_path.is_file():
            raise STGCNModelError("STGCN checkpoint is not installed")
        try:
            import torch

            started = time.perf_counter()
            model = STGCNExtend().to(self.device)
            state = torch.load(
                self.model_path,
                map_location=self.device,
                weights_only=True,
            )
            model.load_state_dict(state, strict=True)
            model.eval()
            self.model = model
            self.model_checksum = _sha256(self.model_path)
            self.model_load_ms = (time.perf_counter() - started) * 1000
        except STGCNModelError:
            raise
        except Exception as exc:
            raise STGCNModelError("STGCN checkpoint could not be loaded") from exc

    def infer(self, sequence: np.ndarray) -> STGCNPrediction:
        if self.model is None:
            raise STGCNModelError("STGCN model is not loaded")
        if sequence.shape != (1, 1, 100, 17, 2):
            raise STGCNModelError("STGCN input has an invalid shape")
        try:
            import torch

            value = torch.from_numpy(sequence).to(self.device)
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            started = time.perf_counter()
            with torch.inference_mode():
                _, logits = self.model(value)
                probabilities = torch.softmax(logits, dim=1)
            if self.device.startswith("cuda"):
                torch.cuda.synchronize()
            self.last_inference_ms = (time.perf_counter() - started) * 1000
            return STGCNPrediction(
                fall_score=float(probabilities[0, 1].item()),
                label_index=int(torch.argmax(probabilities, dim=1).item()),
                latency_ms=self.last_inference_ms,
            )
        except STGCNModelError:
            raise
        except Exception as exc:
            raise STGCNModelError("STGCN inference failed") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
