"""Extract a source interval and convert it to a constant-frame-rate clip."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from .segmentation import Segment, read_video_metadata


@dataclass(frozen=True)
class NormalizedVideo:
    fps: float
    frame_count: int
    width: int
    height: int
    duration_s: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
    for codec in ("mp4v", "avc1"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            return writer
        writer.release()
    raise RuntimeError("OpenCV cannot create an MP4 file; install an OpenCV build with FFmpeg support")


def write_cfr_segment(
    source: str | Path,
    destination: str | Path,
    segment: Segment,
    *,
    target_fps: float = 30.0,
) -> NormalizedVideo:
    """Write ``segment`` as a true constant-frame-rate MP4.

    Frames are selected on the target time grid.  High-frame-rate sources are
    downsampled and low-frame-rate sources are duplicated.  This makes the
    downstream frame index equal to physical time at exactly ``target_fps``.
    """
    if target_fps <= 0:
        raise ValueError("target_fps must be positive")
    source = Path(source)
    destination = Path(destination)
    metadata = read_video_metadata(source)
    if segment.start_frame < 0 or segment.end_frame > metadata.frame_count:
        raise ValueError("segment lies outside the source video")
    if segment.end_frame <= segment.start_frame:
        raise ValueError("segment is empty")

    cap = cv2.VideoCapture(str(source))
    cap.set(cv2.CAP_PROP_POS_FRAMES, segment.start_frame)
    writer: cv2.VideoWriter | None = None
    output_frames = 0
    target_index = 0
    last_frame = None
    source_index = segment.start_frame
    try:
        while source_index < segment.end_frame:
            ok, frame = cap.read()
            if not ok:
                break
            if writer is None:
                writer = _writer(destination, target_fps, (frame.shape[1], frame.shape[0]))
            local_time = (source_index - segment.start_frame) / metadata.fps
            while target_index / target_fps <= local_time + 0.5 / metadata.fps:
                writer.write(frame)
                last_frame = frame
                output_frames += 1
                target_index += 1
            source_index += 1

        desired_frames = max(1, int(round(segment.duration_sec * target_fps)))
        while writer is not None and last_frame is not None and output_frames < desired_frames:
            writer.write(last_frame)
            output_frames += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    if output_frames == 0 or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("constant-frame-rate segment could not be written")
    return NormalizedVideo(
        fps=float(target_fps),
        frame_count=int(output_frames),
        width=metadata.width,
        height=metadata.height,
        duration_s=float(output_frames / target_fps),
    )
