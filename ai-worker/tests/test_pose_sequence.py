import numpy as np

from app.fall_detection.pose import (
    BoundingBox,
    PoseKeypoint,
    PosePerson,
    pose_is_reliable,
)
from app.fall_detection.sequence import PoseSequenceStore


def person(
    track_id: str = "person-1",
    confidence: float = 0.9,
    x: float = 0.25,
) -> PosePerson:
    return PosePerson(
        person_id=track_id,
        bbox=BoundingBox(0.1, 0.2, 0.6, 0.9),
        bbox_confidence=0.9,
        keypoints=tuple(
            PoseKeypoint(str(index), x, 0.75, confidence) for index in range(17)
        ),
    )


def test_sequence_uses_training_coordinate_range_and_shape() -> None:
    store = PoseSequenceStore(
        observed_length=75,
        model_length=100,
        minimum_confidence=0.35,
    )
    for index in range(31):
        store.update((person(),), ("person-1",), index / 15)

    value = store.tensor("person-1")

    assert value.shape == (1, 1, 100, 17, 2)
    assert value.dtype == np.float32
    assert np.allclose(value[0, 0, :75, :, 0], -0.5)
    assert np.allclose(value[0, 0, :75, :, 1], 0.5)
    assert np.count_nonzero(value[0, 0, 75:]) == 0


def test_low_confidence_and_missing_person_are_not_normal_pose() -> None:
    store = PoseSequenceStore(minimum_confidence=0.35)
    store.update((person(confidence=0.1),), ("person-1",), 0.0)
    store.update((), ("person-1",), 0.1)

    assert store.progress("person-1") == 0.05
    assert np.count_nonzero(tuple(store._buffers["person-1"])[0].points) == 0
    assert np.count_nonzero(tuple(store._buffers["person-1"])[1].points) == 0
    assert store.valid_ratio("person-1") == 0.0


def test_sequence_validity_tracks_missing_frames() -> None:
    store = PoseSequenceStore(minimum_confidence=0.35)
    for index in range(25):
        store.update((person(),), ("person-1",), index * 0.08)
    for index in range(6):
        store.update((), ("person-1",), 2.0 + index * 0.01)

    assert store.ready("person-1") is True
    # Only real observations inside the current two-second window count.
    assert store.valid_ratio("person-1") == 24 / 30


def test_two_second_window_is_interpolated_to_75_observed_frames() -> None:
    store = PoseSequenceStore(minimum_confidence=0.35, window_seconds=2.0)
    for index in range(31):
        store.update(
            (person(x=0.2 + index / 100),),
            ("person-1",),
            index / 15,
        )

    value = store.tensor("person-1")

    assert store.progress("person-1") == 1.0
    assert np.isclose(value[0, 0, 0, 0, 0], -0.6)
    assert np.isclose(value[0, 0, 74, 0, 0], 0.0)
    assert np.count_nonzero(value[0, 0, 75:]) == 0


def test_pose_requires_enough_reliable_keypoints() -> None:
    low_pose = person(confidence=0.1)
    reliable_pose = person(confidence=0.9)

    assert pose_is_reliable(low_pose, minimum_confidence=0.35) is False
    assert pose_is_reliable(reliable_pose, minimum_confidence=0.35) is True
