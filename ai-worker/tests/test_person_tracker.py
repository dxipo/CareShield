from app.fall_detection.pose import BoundingBox, PosePerson
from app.fall_detection.tracking import IoUPersonTracker


def detected(box: BoundingBox) -> PosePerson:
    return PosePerson("frame-id", box, 0.9, ())


def test_tracker_preserves_id_across_small_motion() -> None:
    tracker = IoUPersonTracker(minimum_iou=0.2)
    first = tracker.update((detected(BoundingBox(0.1, 0.1, 0.5, 0.9)),))
    second = tracker.update((detected(BoundingBox(0.12, 0.1, 0.52, 0.9)),))

    assert first[0].person_id == "person-1"
    assert second[0].person_id == "person-1"


def test_tracker_keeps_multiple_people_distinct() -> None:
    tracker = IoUPersonTracker(minimum_iou=0.2)
    people = tracker.update(
        (
            detected(BoundingBox(0.05, 0.1, 0.4, 0.9)),
            detected(BoundingBox(0.6, 0.1, 0.95, 0.9)),
        )
    )

    assert {person.person_id for person in people} == {"person-1", "person-2"}


def test_tracker_preserves_id_when_upright_box_becomes_horizontal() -> None:
    tracker = IoUPersonTracker(
        minimum_iou=0.25,
        maximum_center_distance=0.5,
    )
    upright = tracker.update((detected(BoundingBox(0.4, 0.1, 0.6, 0.9)),))
    horizontal = tracker.update((detected(BoundingBox(0.2, 0.55, 0.8, 0.8)),))

    assert upright[0].person_id == horizontal[0].person_id


def test_tracker_retains_last_box_during_short_detection_gap() -> None:
    tracker = IoUPersonTracker(maximum_missing_frames=2)
    first = tracker.update((detected(BoundingBox(0.2, 0.1, 0.6, 0.9)),))
    missing = tracker.update(())

    assert missing[0].person_id == first[0].person_id
    assert missing[0].bbox == first[0].bbox
    assert missing[0].keypoints == ()

    tracker.update(())
    assert tracker.update(()) == ()


def test_new_visible_person_does_not_render_stale_box_as_duplicate() -> None:
    tracker = IoUPersonTracker(maximum_center_distance=0.2)
    first = tracker.update((detected(BoundingBox(0.05, 0.05, 0.25, 0.8)),))
    fallen = tracker.update((detected(BoundingBox(0.35, 0.65, 0.95, 0.9)),))

    assert len(fallen) == 1
    assert fallen[0].person_id == first[0].person_id
