from app.fall_detection.fusion import fuse_person_detections
from app.fall_detection.pose import (
    BoundingBox,
    PersonDetection,
    PoseKeypoint,
    PosePerson,
)


def test_independent_detection_keeps_person_box_when_pose_is_missing() -> None:
    detection = PersonDetection(BoundingBox(0.1, 0.2, 0.8, 0.9), 0.88)

    fused = fuse_person_detections((detection,), ())

    assert len(fused) == 1
    assert fused[0].bbox == detection.bbox
    assert fused[0].keypoints == ()


def test_overlapping_pose_is_attached_to_independent_person_box() -> None:
    detection = PersonDetection(BoundingBox(0.1, 0.2, 0.8, 0.9), 0.88)
    keypoints = tuple(PoseKeypoint(str(index), 0.4, 0.5, 0.9) for index in range(17))
    pose = PosePerson(
        "pose-frame-id",
        BoundingBox(0.12, 0.22, 0.79, 0.88),
        0.7,
        keypoints,
    )

    fused = fuse_person_detections((detection,), (pose,))

    assert len(fused) == 1
    assert fused[0].bbox == detection.bbox
    assert fused[0].keypoints == keypoints


def test_different_box_shapes_for_same_horizontal_person_do_not_duplicate() -> None:
    detection = PersonDetection(BoundingBox(0.1, 0.5, 0.9, 0.8), 0.85)
    keypoints = tuple(PoseKeypoint(str(index), 0.5, 0.65, 0.8) for index in range(17))
    pose = PosePerson(
        "pose-frame-id",
        BoundingBox(0.35, 0.45, 0.68, 0.86),
        0.45,
        keypoints,
    )

    fused = fuse_person_detections((detection,), (pose,))

    assert len(fused) == 1
    assert fused[0].keypoints == keypoints


def test_multiple_detector_boxes_claiming_one_pose_are_deduplicated() -> None:
    detections = (
        PersonDetection(BoundingBox(0.1, 0.4, 0.9, 0.85), 0.9),
        PersonDetection(BoundingBox(0.2, 0.45, 0.62, 0.82), 0.6),
        PersonDetection(BoundingBox(0.55, 0.42, 0.92, 0.8), 0.5),
    )
    keypoints = tuple(PoseKeypoint(str(index), 0.5, 0.65, 0.8) for index in range(17))
    pose = PosePerson(
        "pose-frame-id",
        BoundingBox(0.15, 0.42, 0.88, 0.84),
        0.7,
        keypoints,
    )

    fused = fuse_person_detections(detections, (pose,))

    assert len(fused) == 1
    assert fused[0].keypoints == keypoints
