from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FallDetectionConfig:
    """Fall pipeline parameters; STGCN scores are not clinically calibrated."""

    input_fps: float = 15.0
    input_size: int = 960
    minimum_keypoint_confidence: float = 0.35
    # Retained only for legacy heuristic unit tests; the M5.2 runtime uses the
    # STGCN thresholds below and does not expose these as deployment settings.
    suspected_torso_angle_degrees: float = 45.0
    fallen_torso_angle_degrees: float = 65.0
    downward_velocity_threshold: float = 0.35
    lying_aspect_ratio_threshold: float = 1.15
    suspected_timeout_seconds: float = 1.5
    fallen_persistence_seconds: float = 1.2
    recovery_persistence_seconds: float = 1.5
    result_heartbeat_seconds: float = 1.0
    significant_score_delta: float = 0.15
    sequence_length: int = 100
    observed_sequence_length: int = 75
    observation_window_seconds: float = 2.0
    minimum_sequence_valid_ratio: float = 0.80
    classifier_inference_hz: float = 2.0
    stgcn_suspected_threshold: float = 0.60
    stgcn_fallen_threshold: float = 0.80
    # One result already summarizes a two-second temporal sequence; this is not
    # equivalent to a single-frame fall rule.
    stgcn_confirmation_windows: int = 1
    stgcn_recovery_windows: int = 5
    tracking_minimum_iou: float = 0.25
    tracking_maximum_missing_frames: int = 30
    tracking_maximum_center_distance: float = 0.45

    def __post_init__(self) -> None:
        if self.input_fps <= 0:
            raise ValueError("input_fps must be positive")
        if self.input_size < 32:
            raise ValueError("input_size is too small")
        bounded = (
            self.minimum_keypoint_confidence,
            self.significant_score_delta,
            self.stgcn_suspected_threshold,
            self.stgcn_fallen_threshold,
            self.tracking_minimum_iou,
            self.minimum_sequence_valid_ratio,
            self.tracking_maximum_center_distance,
        )
        if any(value < 0 or value > 1 for value in bounded):
            raise ValueError("confidence and score thresholds must be in [0, 1]")
        if self.sequence_length != 100:
            raise ValueError("the published STGCN-Extend checkpoint requires 100 frames")
        if self.observed_sequence_length != 75:
            raise ValueError("the published STGCN-Extend checkpoint observes 75 frames")
        if self.observation_window_seconds <= 0:
            raise ValueError("observation window must be positive")
        if self.classifier_inference_hz <= 0:
            raise ValueError("classifier_inference_hz must be positive")
        if self.stgcn_suspected_threshold > self.stgcn_fallen_threshold:
            raise ValueError("suspected threshold cannot exceed fallen threshold")
        if self.stgcn_confirmation_windows < 1 or self.stgcn_recovery_windows < 1:
            raise ValueError("decision windows must be positive")
