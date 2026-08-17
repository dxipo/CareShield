from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees

from app.fall_detection.pose import PosePerson


@dataclass(frozen=True, slots=True)
class FallFeatures:
    torso_angle_degrees: float
    shoulder_orientation_degrees: float
    hip_orientation_degrees: float
    hip_center_height: float
    hip_vertical_velocity: float
    body_center_vertical_velocity: float
    bbox_aspect_ratio: float
    skeleton_horizontal_extent: float
    body_height: float
    body_height_change: float
    keypoint_confidence: float


class FallFeatureExtractor:
    """Extract normalized pose geometry without depending on a model framework."""

    def __init__(self) -> None:
        self._previous_timestamp: float | None = None
        self._previous_hip_y: float | None = None
        self._previous_body_y: float | None = None
        self._previous_body_height: float | None = None

    def reset(self) -> None:
        self._previous_timestamp = None
        self._previous_hip_y = None
        self._previous_body_y = None
        self._previous_body_height = None

    def extract(self, person: PosePerson, timestamp_seconds: float) -> FallFeatures | None:
        points = {point.name: point for point in person.keypoints}
        required = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
        if any(name not in points for name in required):
            return None

        left_shoulder, right_shoulder = points["left_shoulder"], points["right_shoulder"]
        left_hip, right_hip = points["left_hip"], points["right_hip"]
        shoulder = _midpoint(left_shoulder.x, left_shoulder.y, right_shoulder.x, right_shoulder.y)
        hip = _midpoint(left_hip.x, left_hip.y, right_hip.x, right_hip.y)
        body = _midpoint(shoulder[0], shoulder[1], hip[0], hip[1])

        bbox_width = max(person.bbox.width, 1e-6)
        bbox_height = max(person.bbox.height, 1e-6)
        torso_angle = degrees(atan2(abs(hip[0] - shoulder[0]), abs(hip[1] - shoulder[1])))
        shoulder_orientation = _line_angle(
            left_shoulder.x,
            left_shoulder.y,
            right_shoulder.x,
            right_shoulder.y,
        )
        hip_orientation = _line_angle(left_hip.x, left_hip.y, right_hip.x, right_hip.y)
        hip_height = (hip[1] - person.bbox.y1) / bbox_height

        visible_x = [point.x for point in person.keypoints if point.confidence > 0]
        horizontal_extent = (
            (max(visible_x) - min(visible_x)) / bbox_width if visible_x else 0.0
        )

        ankle_points = [points[name] for name in ("left_ankle", "right_ankle") if name in points]
        ankle_y = sum(point.y for point in ankle_points) / len(ankle_points) if ankle_points else person.bbox.y2
        body_height = max(0.0, ankle_y - shoulder[1]) / bbox_height

        dt = (
            timestamp_seconds - self._previous_timestamp
            if self._previous_timestamp is not None
            else 0.0
        )
        hip_velocity = _velocity(hip[1], self._previous_hip_y, dt, bbox_height)
        body_velocity = _velocity(body[1], self._previous_body_y, dt, bbox_height)
        body_height_change = (
            (self._previous_body_height - body_height) / dt
            if self._previous_body_height is not None and dt > 1e-6
            else 0.0
        )

        self._previous_timestamp = timestamp_seconds
        self._previous_hip_y = hip[1]
        self._previous_body_y = body[1]
        self._previous_body_height = body_height

        return FallFeatures(
            torso_angle_degrees=_bounded(torso_angle, 0.0, 90.0),
            shoulder_orientation_degrees=shoulder_orientation,
            hip_orientation_degrees=hip_orientation,
            hip_center_height=_bounded(hip_height, 0.0, 1.5),
            hip_vertical_velocity=hip_velocity,
            body_center_vertical_velocity=body_velocity,
            bbox_aspect_ratio=bbox_width / bbox_height,
            skeleton_horizontal_extent=max(0.0, horizontal_extent),
            body_height=body_height,
            body_height_change=body_height_change,
            keypoint_confidence=person.mean_keypoint_confidence,
        )


def _midpoint(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _line_angle(x1: float, y1: float, x2: float, y2: float) -> float:
    return abs(degrees(atan2(y2 - y1, x2 - x1)))


def _velocity(current: float, previous: float | None, dt: float, scale: float) -> float:
    return (current - previous) / dt / scale if previous is not None and dt > 1e-6 else 0.0


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
