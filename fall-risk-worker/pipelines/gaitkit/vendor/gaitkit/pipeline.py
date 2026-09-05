"""Trajectory-to-events-to-parameters analysis service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .config import GaitKitConfig
from .core.types import AnalysisResult, Trajectory
from .events.analytic import AnalyticEventDetector
from .events.base import EventDetector
from .io.trajectory_io import load_trajectory
from .metrics.registry import CANONICAL_METRICS, CORE8, RISK_EXT20, compute_all, metric_manifest
from .preprocess.temporal import resample_trajectory


ANALYSIS_SCHEMA_VERSION = "2.0"
METRIC_DEFINITION_VERSION = "gaitkit-metrics-2.0"


def _json_number(value: object) -> float | int | str | None:
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    return str(value) if isinstance(value, np.str_) else value  # type: ignore[return-value]


class GaitPipeline:
    """Calculate 28 gait parameters from a named three-dimensional trajectory."""

    def __init__(self, config: GaitKitConfig | None = None, event_detector: EventDetector | None = None) -> None:
        self.config = config or GaitKitConfig()
        self.event_detector: EventDetector = event_detector if event_detector is not None else AnalyticEventDetector()

    @staticmethod
    def _resolve(source: Trajectory | str | Path) -> Trajectory:
        return source if isinstance(source, Trajectory) else load_trajectory(source)

    def _select_window(self, trajectory: Trajectory, window: tuple[float, float] | None) -> Trajectory:
        selected = trajectory
        if window is not None:
            start_s, end_s = map(float, window)
            if end_s <= start_s:
                raise ValueError("window end must be later than its start")
            selected = trajectory.copy_window(start_s, end_s)
        if selected.duration_s < self.config.min_segment_s:
            raise ValueError(f"walking segment must be at least {self.config.min_segment_s:.2f} seconds")
        return selected

    def analyse(
        self,
        source: Trajectory | str | Path,
        height_mm: float,
        window: tuple[float, float] | None = None,
    ) -> AnalysisResult:
        low, high = self.config.height_range_mm
        if not np.isfinite(height_mm) or not low <= height_mm <= high:
            raise ValueError(f"height_mm must be between {low:g} and {high:g}")
        available, hint = self.event_detector.available()
        if not available:
            raise RuntimeError(f"event detector {self.event_detector.name!r} is unavailable: {hint}")

        selected = self._select_window(self._resolve(source), window)
        sampled = (
            resample_trajectory(selected, self.config.target_fps)
            if abs(selected.fps - self.config.target_fps) > 0.1
            else selected
        )
        events = self.event_detector.detect(sampled, height_mm)
        if events.total_heel_strikes < 6:
            raise ValueError("at least six heel strikes are required to calculate all 28 parameters")
        if not sampled.world_grounded:
            raise ValueError("all 28 parameters require a metre-scale world-grounded skeleton")
        metrics_raw: dict[str, Any] = compute_all(sampled, events)
        metrics_raw.update(
            n_left_hs=events.n_left_hs,
            n_right_hs=events.n_right_hs,
            event_detector=events.detector,
            spatial_valid=int(sampled.world_grounded),
        )
        metrics = {key: _json_number(value) for key, value in metrics_raw.items()}
        missing = [name for name in CANONICAL_METRICS if metrics.get(name) is None]
        if missing:
            raise ValueError("unable to calculate all 28 parameters: " + ", ".join(missing))

        return AnalysisResult(
            schema_version=ANALYSIS_SCHEMA_VERSION,
            metrics=metrics,
            events={
                "left_heel_strike_s": events.left_down.astype(float).tolist(),
                "right_heel_strike_s": events.right_down.astype(float).tolist(),
                "left_toe_off_s": events.left_up.astype(float).tolist(),
                "right_toe_off_s": events.right_up.astype(float).tolist(),
                "detector": events.detector,
                "metadata": dict(events.metadata),
            },
            provenance={
                "source": sampled.source,
                "height_mm": float(height_mm),
                "segment_start_s": float(sampled.time_s[0]),
                "segment_end_s": float(sampled.time_s[-1]),
                "up_axis": int(sampled.up_axis),
                "world_grounded": bool(sampled.world_grounded),
                "event_model": events.detector,
                "metric_definition_version": METRIC_DEFINITION_VERSION,
                "metric_sets": {"core": list(CORE8), "risk_extended": list(RISK_EXT20)},
            },
        )

    @staticmethod
    def metric_manifest() -> list[dict[str, str]]:
        return metric_manifest()
