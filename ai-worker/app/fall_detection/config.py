from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FallDetectionConfig:
    """M5 baseline heuristic parameters; these are not clinically validated."""

    input_fps: float = 5.0
    input_size: int = 640
    minimum_keypoint_confidence: float = 0.35
    suspected_torso_angle_degrees: float = 45.0
    fallen_torso_angle_degrees: float = 65.0
    downward_velocity_threshold: float = 0.35
    lying_aspect_ratio_threshold: float = 1.15
    suspected_timeout_seconds: float = 1.5
    fallen_persistence_seconds: float = 1.2
    recovery_persistence_seconds: float = 1.5
    result_heartbeat_seconds: float = 1.0
    significant_score_delta: float = 0.15

    def __post_init__(self) -> None:
        if self.input_fps <= 0:
            raise ValueError("input_fps must be positive")
        if self.input_size < 32:
            raise ValueError("input_size is too small")
        bounded = (
            self.minimum_keypoint_confidence,
            self.significant_score_delta,
        )
        if any(value < 0 or value > 1 for value in bounded):
            raise ValueError("confidence and score thresholds must be in [0, 1]")
