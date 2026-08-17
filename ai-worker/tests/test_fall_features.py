from app.fall_detection.features import FallFeatureExtractor
from app.fall_detection.pose import BoundingBox, PoseKeypoint, PosePerson


def person(*, horizontal: bool = False) -> PosePerson:
    if horizontal:
        coordinates = {
            "left_shoulder": (0.25, 0.58),
            "right_shoulder": (0.35, 0.62),
            "left_hip": (0.62, 0.60),
            "right_hip": (0.72, 0.64),
            "left_ankle": (0.78, 0.63),
            "right_ankle": (0.82, 0.67),
        }
        bbox = BoundingBox(0.2, 0.45, 0.85, 0.75)
    else:
        coordinates = {
            "left_shoulder": (0.45, 0.30),
            "right_shoulder": (0.55, 0.30),
            "left_hip": (0.46, 0.55),
            "right_hip": (0.54, 0.55),
            "left_ankle": (0.47, 0.90),
            "right_ankle": (0.53, 0.90),
        }
        bbox = BoundingBox(0.35, 0.20, 0.65, 0.95)
    return PosePerson(
        person_id="synthetic-person",
        bbox=bbox,
        bbox_confidence=0.9,
        keypoints=tuple(
            PoseKeypoint(name=name, x=x, y=y, confidence=0.9)
            for name, (x, y) in coordinates.items()
        ),
    )


def test_normalized_features_capture_torso_angle_and_downward_velocity() -> None:
    extractor = FallFeatureExtractor()
    standing = extractor.extract(person(), 0.0)
    falling = extractor.extract(person(horizontal=True), 0.2)

    assert standing is not None and standing.torso_angle_degrees < 5
    assert falling is not None
    assert falling.torso_angle_degrees > 75
    assert falling.hip_vertical_velocity > 0
    assert falling.bbox_aspect_ratio > 1
    assert 0 <= falling.keypoint_confidence <= 1
