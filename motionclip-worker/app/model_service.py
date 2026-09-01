"""Long-lived, GPU-backed MotionCLIP inference service."""

from __future__ import annotations

import threading
from pathlib import Path

import torch

from app.input_adapter import load_gvhmr_windows
from app.model_runtime import CONCEPT_LEVELS, load_model
from app.risk_classification import classify_risk, load_risk_thresholds


class MotionClipService:
    def __init__(
        self,
        profile_name: str,
        checkpoint: str,
        device_name: str,
        risk_thresholds_path: Path,
    ) -> None:
        if device_name == "auto":
            device_name = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device_name)
        self.model, _ = load_model(checkpoint, self.device)
        self.risk_calibration = load_risk_thresholds(risk_thresholds_path)
        self.model_info = {
            "profile_id": profile_name,
            "display_name": "CARE-PD 四数据集可解释模型",
            "status": "active_default",
            "architecture": "carepd_encoder_only_reference_difference_v1",
            "training_scope": "BMCLab, PD-GaM, T-SDU-PD and 3DGait",
            "checkpoint_epoch": 13,
            "web_interface_compatible": True,
            "clinical_risk_calibrated": False,
        }
        self._lock = threading.Lock()

    @property
    def runtime_info(self) -> dict[str, object]:
        return {
            "ready": True,
            "device": str(self.device),
            "cuda_available": torch.cuda.is_available(),
            "model": self.model_info,
        }

    def predict_gvhmr(self, path: Path) -> dict[str, object]:
        windows, metadata = load_gvhmr_windows(path)
        x = torch.from_numpy(windows)
        batch_size = len(x)
        batch = {
            "x": x,
            "y": torch.zeros(batch_size, dtype=torch.long),
            "mask": torch.ones(batch_size, 60, dtype=torch.bool),
            "lengths": torch.full((batch_size,), 60, dtype=torch.long),
        }
        with self._lock:
            model_batch = {key: value.to(self.device) for key, value in batch.items()}
            with torch.inference_mode():
                output = self.model(model_batch)
        distance = float(output["healthy_distance"].float().mean().cpu())
        thresholds = self.risk_calibration["thresholds"]
        if not isinstance(thresholds, dict):
            raise RuntimeError("Risk thresholds are unavailable")
        risk_level = classify_risk(distance, thresholds)
        probabilities = output["concept_probabilities"].float().mean(dim=0).cpu()
        concepts: dict[str, object] = {}
        for index, name in enumerate(self.model.concept_names):
            levels = CONCEPT_LEVELS[name]
            values = probabilities[index, : len(levels)]
            top_values, top_indices = torch.topk(values, k=2)
            concepts[name] = {
                "predicted_level": levels[int(top_indices[0])],
                "predicted_level_id": int(top_indices[0]),
                "probabilities": {
                    level: float(values[level_index])
                    for level_index, level in enumerate(levels)
                },
                "top1_probability": float(top_values[0]),
                "second_best_probability": float(top_values[1]),
                "margin": float(top_values[0] - top_values[1]),
            }
        return {
            "model": self.model_info,
            "metadata": {
                **metadata,
                "aggregation": "equal_mean_of_window_distances_and_concept_probabilities",
                "coordinate_note": "GVHMR global SMPL-X parameters mapped to CARE-PD SMPL joint order; no clinical domain calibration",
                "risk_classification": self.risk_calibration,
            },
            "healthy_distance": distance,
            "risk_level": risk_level,
            "concepts": concepts,
            "explanation": render_explanation(distance, risk_level, concepts),
        }


def render_explanation(distance: float, risk_level: str, concepts: dict[str, object]) -> str:
    concept_zh = {
        "step_length": "步幅", "walking_speed": "行走速度", "foot_lift": "足部抬升",
        "arm_swing": "摆臂幅度", "cadence": "步频", "step_width": "步宽",
        "lateral_stability": "横向稳定性", "stoop_posture": "弯腰姿势",
    }
    level_zh = {
        "normal": "正常", "mild": "轻度异常", "moderate": "中度异常",
        "marked": "显著异常", "abnormal": "异常",
    }
    risk_zh = {"low": "低风险", "medium": "中风险", "high": "高风险"}
    descriptions = [
        f"{concept_zh[name]}：{level_zh[value['predicted_level']]}"
        for name, value in concepts.items()
    ]
    return (
        f"跌倒风险等级：{risk_zh[risk_level]}\n"
        f"健康参考偏离程度：{distance:.6f}\n\n"
        "八项模型概念：" + "；".join(descriptions) + "。"
    )
