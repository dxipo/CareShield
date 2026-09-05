"""Numerical constants shared by gait event and parameter analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GaitKitConfig:
    target_fps: float = 30.0
    event_window_frames: int = 60
    min_segment_s: float = 3.0
    height_range_mm: tuple[float, float] = (800.0, 2500.0)

    def __post_init__(self) -> None:
        if self.target_fps <= 0:
            raise ValueError("target_fps must be positive")
        if self.event_window_frames < 2:
            raise ValueError("event_window_frames must be at least two")
        if self.min_segment_s <= 0:
            raise ValueError("min_segment_s must be positive")
        low, high = self.height_range_mm
        if not 0 < low < high:
            raise ValueError("height_range_mm is invalid")
