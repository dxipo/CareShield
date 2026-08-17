from app.fall_detection.config import FallDetectionConfig
from app.fall_detection.detector import FallState, TemporalFallDetector
from app.fall_detection.features import FallFeatures


def features(*, angle: float, velocity: float, aspect: float) -> FallFeatures:
    return FallFeatures(
        torso_angle_degrees=angle,
        shoulder_orientation_degrees=0,
        hip_orientation_degrees=0,
        hip_center_height=0.5,
        hip_vertical_velocity=velocity,
        body_center_vertical_velocity=velocity,
        bbox_aspect_ratio=aspect,
        skeleton_horizontal_extent=0.5,
        body_height=0.8,
        body_height_change=max(0.0, velocity / 2),
        keypoint_confidence=0.9,
    )


def test_temporal_fall_requires_descent_and_lying_persistence_then_recovers() -> None:
    detector = TemporalFallDetector(FallDetectionConfig())
    falling = features(angle=75, velocity=0.8, aspect=1.3)
    lying = features(angle=82, velocity=0.0, aspect=1.6)
    upright = features(angle=5, velocity=0.0, aspect=0.4)

    assert detector.update(falling, 0.0).state == FallState.SUSPECTED_FALL
    assert detector.update(lying, 0.6).state == FallState.SUSPECTED_FALL
    assert detector.update(lying, 1.3).state == FallState.FALLEN
    assert detector.update(upright, 2.0).state == FallState.FALLEN
    assert detector.update(upright, 3.6).state == FallState.RECOVERING
    assert detector.update(upright, 5.2).state == FallState.NORMAL


def test_bending_or_static_lying_does_not_single_frame_trigger_fall() -> None:
    detector = TemporalFallDetector(FallDetectionConfig())
    bending = features(angle=55, velocity=0.0, aspect=0.6)
    static_lying = features(angle=85, velocity=0.0, aspect=1.7)

    assert detector.update(bending, 0.0).state == FallState.NORMAL
    assert detector.update(static_lying, 1.0).state == FallState.NORMAL


def test_heuristic_score_is_bounded() -> None:
    detector = TemporalFallDetector(FallDetectionConfig())
    assert detector.update(features(angle=-100, velocity=-10, aspect=-1), 0).score == 0
    assert 0.999 <= detector.update(features(angle=1000, velocity=100, aspect=100), 1).score <= 1
