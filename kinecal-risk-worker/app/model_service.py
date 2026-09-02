"""Long-lived KINECAL fall-risk inference service."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import numpy as np
import torch

from app.input_adapter import load_world_skeleton
from app.model_runtime import ActionAdapterRiskClassifier


RISK_LEVELS = ("low", "medium", "high")
GROUPS = ("NF", "FHs", "FHm")


class KinecalRiskService:
    def __init__(self, checkpoint: Path, profile_path: Path, device_name: str) -> None:
        self.profile = json.loads(profile_path.read_text(encoding="utf-8"))
        expected = self.profile["checkpoint_sha256"]
        actual = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("KINECAL checkpoint checksum mismatch")
        payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
        args = payload.get("args", {})
        action_map = payload.get("action_map", {})
        if not (
            args.get("clip_len") == 120
            and args.get("duration_norm") == "global"
            and args.get("action_adapter") is True
            and action_map.get("3m-walk-Front-View") == 0
        ):
            raise ValueError("Unsupported KINECAL checkpoint contract")
        if device_name == "auto":
            device_name = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device_name)
        self.action_id = int(action_map["3m-walk-Front-View"])
        self.model = ActionAdapterRiskClassifier(
            num_actions=len(action_map),
            adapter_dim=int(args["adapter_dim"]),
            adapter_scale=float(args["adapter_scale"]),
        ).to(self.device)
        self.model.load_state_dict(payload["state_dict"], strict=True)
        self.model.eval().requires_grad_(False)
        self._lock = threading.Lock()

    @property
    def runtime_info(self) -> dict[str, object]:
        return {
            "ready": True,
            "device": str(self.device),
            "cuda_available": torch.cuda.is_available(),
            "model": self.profile["model"],
        }

    def predict(self, path: Path) -> dict[str, object]:
        skeleton, metadata = load_world_skeleton(path)
        duration = float(metadata["source_duration_seconds"])
        duration_stats = self.profile["duration_normalization"]
        duration_value = (duration - float(duration_stats["mean_seconds"])) / float(
            duration_stats["std_seconds"]
        )
        value = torch.from_numpy(skeleton[None]).to(self.device)
        duration_tensor = torch.tensor([[duration_value]], dtype=torch.float32, device=self.device)
        action_tensor = torch.tensor([self.action_id], dtype=torch.long, device=self.device)
        with self._lock, torch.inference_mode():
            raw_logits = self.model(value, duration_tensor, action_tensor)[0].float().cpu()
        raw_probabilities = raw_logits.softmax(dim=0).numpy()
        calibration = self.profile["action_calibration"]
        calibrated_logits = (
            raw_logits.numpy() * np.asarray(calibration["scale"], dtype=np.float32)
            + np.asarray(calibration["bias"], dtype=np.float32)
        )
        calibrated_probabilities = torch.from_numpy(calibrated_logits).softmax(dim=0).numpy()
        predicted_class = int(np.argmax(calibrated_probabilities))
        probabilities = {
            level: float(calibrated_probabilities[index])
            for index, level in enumerate(RISK_LEVELS)
        }
        raw = {
            level: float(raw_probabilities[index])
            for index, level in enumerate(RISK_LEVELS)
        }
        confidence = float(calibrated_probabilities[predicted_class])
        limitations = list(self.profile["limitations"])
        input_quality = "usable" if confidence >= float(self.profile["review_below_confidence"]) else "review"
        if input_quality == "review":
            limitations.insert(0, "分类置信度不足，建议重新采集并结合其他评估项目复核")
        return {
            "model": self.profile["model"],
            "risk_level": RISK_LEVELS[predicted_class],
            "predicted_class": predicted_class,
            "predicted_group": GROUPS[predicted_class],
            "class_probabilities": probabilities,
            "raw_class_probabilities": raw,
            "confidence": confidence,
            "action_type": "3m-walk-Front-View",
            **metadata,
            "clip_frames": 120,
            "input_quality": input_quality,
            "limitations": limitations,
            "metadata": {
                "duration_zscore": duration_value,
                "calibration": calibration,
                "label_mapping": {"0": "NF", "1": "FHs", "2": "FHm"},
                "coordinate_adapter": metadata["input_adapter"],
            },
        }
