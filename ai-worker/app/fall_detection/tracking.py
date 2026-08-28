from __future__ import annotations

from dataclasses import replace

from app.fall_detection.pose import BoundingBox, PosePerson


class IoUPersonTracker:
    """Small deterministic tracker that stabilizes per-frame YOLO person IDs."""

    def __init__(
        self,
        minimum_iou: float = 0.25,
        maximum_missing_frames: int = 30,
        maximum_center_distance: float = 0.45,
    ) -> None:
        self.minimum_iou = minimum_iou
        self.maximum_missing_frames = maximum_missing_frames
        self.maximum_center_distance = maximum_center_distance
        self._next_id = 1
        self._tracks: dict[str, BoundingBox] = {}
        self._missing: dict[str, int] = {}

    def update(self, persons: tuple[PosePerson, ...]) -> tuple[PosePerson, ...]:
        candidates = {
            (track_id, index): (
                _iou(box, person.bbox),
                _center_distance(box, person.bbox),
            )
            for track_id, box in self._tracks.items()
            for index, person in enumerate(persons)
        }
        assignments: dict[int, str] = {}
        used_tracks: set[str] = set()
        for (track_id, index), (overlap, distance) in sorted(
            candidates.items(),
            key=lambda item: (item[1][0], -item[1][1]),
            reverse=True,
        ):
            if (
                overlap < self.minimum_iou
                and distance > self.maximum_center_distance
            ) or track_id in used_tracks or index in assignments:
                continue
            assignments[index] = track_id
            used_tracks.add(track_id)

        # In the expected single-person home scene, a fall can move the box
        # center farther than the normal gate in one sampled frame. Reassociate
        # that sole observation with the nearest live track instead of creating
        # a second ID. Multi-person scenes keep the stricter assignment above.
        if len(persons) == 1 and 0 not in assignments and self._tracks:
            nearest_track, nearest_distance = min(
                (
                    (track_id, _center_distance(box, persons[0].bbox))
                    for track_id, box in self._tracks.items()
                    if track_id not in used_tracks
                ),
                key=lambda item: item[1],
                default=(None, float("inf")),
            )
            if nearest_track is not None and nearest_distance <= 0.80:
                assignments[0] = nearest_track
                used_tracks.add(nearest_track)

        tracked: list[PosePerson] = []
        for index, person in enumerate(persons):
            track_id = assignments.get(index)
            if track_id is None:
                track_id = f"person-{self._next_id}"
                self._next_id += 1
            self._tracks[track_id] = person.bbox
            self._missing[track_id] = 0
            tracked.append(replace(person, person_id=track_id))

        visible = {person.person_id for person in tracked}
        for track_id in tuple(self._tracks):
            if track_id in visible:
                continue
            self._missing[track_id] = self._missing.get(track_id, 0) + 1
            if self._missing[track_id] > self.maximum_missing_frames:
                self._tracks.pop(track_id, None)
                self._missing.pop(track_id, None)
        # Preserve the last known box briefly when both detector and pose miss
        # a frame. Keypoints remain empty, so this can never be classified as a
        # reliable pose or silently treated as NORMAL.
        if not tracked:
            retained = min(
                self._tracks,
                key=lambda track_id: self._missing.get(track_id, 0),
                default=None,
            )
            if retained is not None:
                box = self._tracks[retained]
                tracked.append(
                    PosePerson(
                        person_id=retained,
                        bbox=box,
                        bbox_confidence=0.0,
                        keypoints=(),
                    )
                )
        return tuple(tracked)

    @property
    def active_track_ids(self) -> tuple[str, ...]:
        return tuple(self._tracks)

    def reset(self) -> None:
        self._tracks.clear()
        self._missing.clear()
        self._next_id = 1


def _iou(first: BoundingBox, second: BoundingBox) -> float:
    left = max(first.x1, second.x1)
    top = max(first.y1, second.y1)
    right = min(first.x2, second.x2)
    bottom = min(first.y2, second.y2)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union > 0 else 0.0


def _center_distance(first: BoundingBox, second: BoundingBox) -> float:
    first_x = (first.x1 + first.x2) / 2
    first_y = (first.y1 + first.y2) / 2
    second_x = (second.x1 + second.x2) / 2
    second_y = (second.y1 + second.y2) / 2
    return ((first_x - second_x) ** 2 + (first_y - second_y) ** 2) ** 0.5
