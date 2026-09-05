from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gaitkit.video import Segment, read_video_metadata, write_cfr_segment


def test_cfr_segment_converts_20hz_to_30hz(tmp_path: Path) -> None:
    source = tmp_path / "source.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 20.0, (96, 64))
    assert writer.isOpened()
    for index in range(80):
        frame = np.full((64, 96, 3), index % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    segment = Segment(1, 10, 70, 20.0, 1.0, 1.0, 1.0)
    destination = tmp_path / "segment.mp4"
    normalized = write_cfr_segment(source, destination, segment, target_fps=30.0)
    metadata = read_video_metadata(destination)
    assert normalized.frame_count == 90
    assert metadata.frame_count == 90
    assert abs(metadata.fps - 30.0) < 0.1
