from dataclasses import dataclass
from enum import Enum

from app.fall_detection.config import FallDetectionConfig
from app.fall_detection.features import FallFeatures


class FallState(str, Enum):
    NORMAL = "normal"
    SUSPECTED_FALL = "suspected_fall"
    FALLEN = "fallen"
    RECOVERING = "recovering"


@dataclass(frozen=True, slots=True)
class FallDecision:
    state: FallState
    score: float
    state_changed: bool
    features: FallFeatures


class TemporalFallDetector:
    """A transparent M5 state machine, not a clinically calibrated classifier."""

    def __init__(self, config: FallDetectionConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.state = FallState.NORMAL
        self._state_since: float | None = None
        self._lying_since: float | None = None
        self._upright_since: float | None = None

    def update(self, features: FallFeatures, timestamp_seconds: float) -> FallDecision:
        previous = self.state
        score = self._fall_score(features)
        rapid_descent = (
            max(features.hip_vertical_velocity, features.body_center_vertical_velocity)
            >= self.config.downward_velocity_threshold
        )
        tilted = features.torso_angle_degrees >= self.config.suspected_torso_angle_degrees
        lying = (
            features.torso_angle_degrees >= self.config.fallen_torso_angle_degrees
            or features.bbox_aspect_ratio >= self.config.lying_aspect_ratio_threshold
        )
        upright = (
            features.torso_angle_degrees < self.config.suspected_torso_angle_degrees * 0.7
            and features.bbox_aspect_ratio < self.config.lying_aspect_ratio_threshold * 0.8
        )

        if self.state == FallState.NORMAL:
            if rapid_descent and tilted:
                self._enter(FallState.SUSPECTED_FALL, timestamp_seconds)
                self._lying_since = timestamp_seconds if lying else None
        elif self.state == FallState.SUSPECTED_FALL:
            self._lying_since = self._continued_since(self._lying_since, lying, timestamp_seconds)
            if self._elapsed(self._lying_since, timestamp_seconds) >= self.config.fallen_persistence_seconds:
                self._enter(FallState.FALLEN, timestamp_seconds)
            elif not tilted and not rapid_descent:
                self._enter(FallState.NORMAL, timestamp_seconds)
            elif self._elapsed(self._state_since, timestamp_seconds) > self.config.suspected_timeout_seconds and not lying:
                self._enter(FallState.NORMAL, timestamp_seconds)
        elif self.state == FallState.FALLEN:
            self._upright_since = self._continued_since(self._upright_since, upright, timestamp_seconds)
            if self._elapsed(self._upright_since, timestamp_seconds) >= self.config.recovery_persistence_seconds:
                self._enter(FallState.RECOVERING, timestamp_seconds)
        elif self.state == FallState.RECOVERING:
            if lying:
                self._enter(FallState.FALLEN, timestamp_seconds)
            else:
                self._upright_since = self._continued_since(self._upright_since, upright, timestamp_seconds)
                if self._elapsed(self._upright_since, timestamp_seconds) >= self.config.recovery_persistence_seconds:
                    self._enter(FallState.NORMAL, timestamp_seconds)

        return FallDecision(
            state=self.state,
            score=score,
            state_changed=self.state != previous,
            features=features,
        )

    def _enter(self, state: FallState, timestamp_seconds: float) -> None:
        self.state = state
        self._state_since = timestamp_seconds
        self._lying_since = None
        self._upright_since = timestamp_seconds if state == FallState.RECOVERING else None

    def _fall_score(self, features: FallFeatures) -> float:
        """Bounded heuristic evidence score; it is deliberately not a probability."""

        angle = _ramp(features.torso_angle_degrees, 30.0, 85.0)
        velocity = _ramp(
            max(features.hip_vertical_velocity, features.body_center_vertical_velocity),
            0.1,
            self.config.downward_velocity_threshold * 2.0,
        )
        aspect = _ramp(features.bbox_aspect_ratio, 0.65, 1.5)
        height_change = _ramp(features.body_height_change, 0.05, 0.8)
        score = 0.35 * angle + 0.30 * velocity + 0.25 * aspect + 0.10 * height_change
        return max(0.0, min(1.0, score))

    @staticmethod
    def _continued_since(current: float | None, condition: bool, now: float) -> float | None:
        if not condition:
            return None
        return current if current is not None else now

    @staticmethod
    def _elapsed(start: float | None, now: float) -> float:
        return max(0.0, now - start) if start is not None else 0.0


def _ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))
