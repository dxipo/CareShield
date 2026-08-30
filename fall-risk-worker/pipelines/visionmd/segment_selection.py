"""Pure helpers for selecting one continuous, observable walking segment."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class FrameSegment:
    start: int
    end: int
    valid_frames: int

    @property
    def frame_count(self) -> int:
        return self.end - self.start


def select_continuous_segment(
    valid: Iterable[object],
    fps: float,
    *,
    bridge_gap_seconds: float = 0.75,
    minimum_duration_seconds: float = 2.0,
) -> FrameSegment:
    """Select the strongest continuous person track without bridging long absences.

    Short detector misses remain inside a segment and can be interpolated. Leading,
    trailing, and long internal no-person intervals are never included.
    """

    indices = [index for index, item in enumerate(valid) if bool(item)]
    if not indices:
        raise ValueError("Video does not contain an observable person")
    frames_per_second = fps if fps > 0 else 30.0
    maximum_gap = max(1, int(round(bridge_gap_seconds * frames_per_second)))
    groups: list[FrameSegment] = []
    group_start = 0
    for position in range(1, len(indices)):
        missing_between = int(indices[position] - indices[position - 1] - 1)
        if missing_between > maximum_gap:
            selected = indices[group_start:position]
            groups.append(
                FrameSegment(
                    start=int(selected[0]),
                    end=int(selected[-1]) + 1,
                    valid_frames=len(selected),
                )
            )
            group_start = position
    selected = indices[group_start:]
    groups.append(
        FrameSegment(
            start=int(selected[0]),
            end=int(selected[-1]) + 1,
            valid_frames=len(selected),
        )
    )
    best = max(groups, key=lambda item: (item.valid_frames, item.frame_count))
    if best.frame_count / frames_per_second < minimum_duration_seconds:
        raise ValueError("No continuous walking segment is long enough for assessment")
    return best
