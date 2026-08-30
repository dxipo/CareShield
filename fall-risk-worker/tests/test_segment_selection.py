from pathlib import Path
import sys

import pytest


VISIONMD_ROOT = Path(__file__).resolve().parents[1] / "pipelines" / "visionmd"
sys.path.insert(0, str(VISIONMD_ROOT))

from segment_selection import select_continuous_segment  # noqa: E402


def test_leading_and_trailing_no_person_frames_are_excluded() -> None:
    valid = [False] * 5 + [True] * 170 + [False] * 29

    segment = select_continuous_segment(valid, 24.0)

    assert (segment.start, segment.end) == (5, 175)
    assert segment.frame_count == 170


def test_long_internal_absence_splits_tracks_and_selects_strongest() -> None:
    valid = [True] * 60 + [False] * 140 + [True] * 100

    segment = select_continuous_segment(valid, 24.0)

    assert (segment.start, segment.end) == (200, 300)


def test_short_detector_dropout_remains_inside_the_same_segment() -> None:
    valid = [True] * 30 + [False] * 10 + [True] * 30

    segment = select_continuous_segment(valid, 24.0)

    assert (segment.start, segment.end) == (0, 70)


def test_video_without_a_person_is_rejected() -> None:
    with pytest.raises(ValueError, match="observable person"):
        select_continuous_segment([False] * 120, 24.0)
