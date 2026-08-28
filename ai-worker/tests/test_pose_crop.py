from datetime import datetime, timezone

import pytest

from app.fall_detection.pose import (
    BoundingBox,
    PoseFrame,
    PoseKeypoint,
    PosePerson,
)
from app.fall_detection.pose_estimator import _remap_pose_frame, _unrotate_pose_frame


def test_crop_pose_coordinates_are_mapped_back_to_full_frame() -> None:
    cropped = PoseFrame(
        timestamp=datetime.now(timezone.utc),
        source_width=100,
        source_height=100,
        persons=(
            PosePerson(
                person_id="crop-person",
                bbox=BoundingBox(0.1, 0.2, 0.9, 0.8),
                bbox_confidence=0.8,
                keypoints=(PoseKeypoint("nose", 0.5, 0.5, 0.9),),
            ),
        ),
        inference_ms=5.0,
    )

    remapped = _remap_pose_frame(
        cropped,
        BoundingBox(0.2, 0.4, 0.8, 0.9),
        1920,
        1080,
    )

    assert remapped.source_width == 1920
    assert remapped.source_height == 1080
    assert remapped.persons[0].keypoints[0].x == pytest.approx(0.5)
    assert remapped.persons[0].keypoints[0].y == pytest.approx(0.65)
    bbox = remapped.persons[0].bbox
    assert (bbox.x1, bbox.y1, bbox.x2, bbox.y2) == pytest.approx(
        (0.26, 0.5, 0.74, 0.8)
    )


def test_clockwise_pose_is_mapped_back_to_original_crop_orientation() -> None:
    rotated = PoseFrame(
        timestamp=datetime.now(timezone.utc),
        source_width=200,
        source_height=100,
        persons=(
            PosePerson(
                person_id="rotated",
                bbox=BoundingBox(0.2, 0.3, 0.8, 0.7),
                bbox_confidence=0.8,
                keypoints=(PoseKeypoint("nose", 0.25, 0.6, 0.9),),
            ),
        ),
        inference_ms=4.0,
    )

    original = _unrotate_pose_frame(rotated, "clockwise")

    point = original.persons[0].keypoints[0]
    assert (point.x, point.y) == pytest.approx((0.6, 0.75))
    bbox = original.persons[0].bbox
    assert (bbox.x1, bbox.y1, bbox.x2, bbox.y2) == pytest.approx(
        (0.3, 0.2, 0.7, 0.8)
    )
