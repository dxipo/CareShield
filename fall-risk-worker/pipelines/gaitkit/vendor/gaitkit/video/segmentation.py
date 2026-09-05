"""Walking-segment detection using lightweight, explainable video signals.

The default backend does not require a neural-network checkpoint.  It combines
an adaptive-background foreground box with frame-difference motion energy, then
fills short gaps and removes short runs.  A detector callable (for example,
Ultralytics YOLO) can be passed to obtain a more reliable person box while the
temporal logic remains unchanged.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

import cv2
import numpy as np


BBox = tuple[int, int, int, int]
Detector = Callable[[np.ndarray], Optional[BBox]]


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    fps: float
    frame_count: int
    width: int
    height: int
    duration_sec: float


@dataclass(frozen=True)
class FrameObservation:
    frame_index: int
    time_sec: float
    motion_energy: float
    presence: bool
    score: float
    bbox: Optional[BBox]


@dataclass(frozen=True)
class Segment:
    """A half-open source-video interval [start_frame, end_frame)."""

    index: int
    start_frame: int
    end_frame: int
    fps: float
    presence_ratio: float
    activity_ratio: float
    confidence: float

    @property
    def duration_sec(self) -> float:
        return (self.end_frame - self.start_frame) / self.fps

    def to_dict(self) -> dict:
        value = asdict(self)
        value["duration_sec"] = round(self.duration_sec, 4)
        return value


def read_video_metadata(video_path: Path) -> VideoMetadata:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频：{video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
        raise RuntimeError(f"视频元数据无效：{video_path}")
    return VideoMetadata(
        # Keep the manifest portable and privacy-safe.  The absolute path is
        # used internally by OpenCV, but is never written to the output JSON.
        path=video_path.name,
        fps=fps,
        frame_count=frame_count,
        width=width,
        height=height,
        duration_sec=frame_count / fps,
    )


def _largest_foreground_bbox(mask: np.ndarray, min_pixels: int) -> Optional[BBox]:
    """Return the largest connected foreground component as x,y,w,h."""
    cleaned = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
        iterations=1,
    )
    cleaned = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_CLOSE,
        np.ones((7, 7), dtype=np.uint8),
        iterations=2,
    )
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(cleaned, 8)
    if num_labels <= 1:
        return None
    best = None
    best_area = 0
    for label in range(1, num_labels):
        x, y, w, h, area = stats[label].tolist()
        if area >= min_pixels and area > best_area:
            best = (int(x), int(y), int(w), int(h))
            best_area = int(area)
    return best


def _valid_bbox(bbox: Optional[BBox], width: int, height: int) -> bool:
    if bbox is None:
        return False
    _, _, w, h = bbox
    area_ratio = (w * h) / float(width * height)
    aspect = w / max(h, 1)
    # A person box should be neither a one-pixel noise blob nor the whole frame.
    return 0.002 <= area_ratio <= 0.85 and 0.08 <= aspect <= 2.5 and h >= 0.08 * height


def _fill_short_gaps(values: np.ndarray, max_gap: int) -> np.ndarray:
    result = values.astype(bool).copy()
    if max_gap <= 0:
        return result
    n = len(result)
    i = 0
    while i < n:
        if result[i]:
            i += 1
            continue
        start = i
        while i < n and not result[i]:
            i += 1
        end = i
        if start > 0 and end < n and end - start <= max_gap:
            result[start:end] = True
    return result


def _remove_short_runs(values: np.ndarray, min_run: int) -> np.ndarray:
    result = values.astype(bool).copy()
    if min_run <= 1:
        return result
    n = len(result)
    i = 0
    while i < n:
        state = bool(result[i])
        start = i
        while i < n and bool(result[i]) == state:
            i += 1
        if state and i - start < min_run:
            result[start:i] = False
    return result


def _runs(values: Sequence[bool]) -> Iterable[tuple[int, int]]:
    start: Optional[int] = None
    for i, value in enumerate(values):
        if value and start is None:
            start = i
        elif not value and start is not None:
            yield start, i
            start = None
    if start is not None:
        yield start, len(values)


class MotionWalkingSegmenter:
    """Detect continuous walking candidates from an RGB video.

    The result is deliberately a candidate interval rather than a clinical
    gait-event label.  HS/TO detection remains a downstream responsibility of
    the 3D skeleton/gait module.
    """

    def __init__(
        self,
        min_segment_sec: float = 3.0,
        max_gap_sec: float = 1.0,
        analysis_fps: float = 15.0,
        min_motion: float = 0.0015,
        min_presence_ratio: float = 0.25,
        analysis_width: int = 640,
    ) -> None:
        if min_segment_sec <= 0 or max_gap_sec < 0 or analysis_fps <= 0:
            raise ValueError("时间参数必须满足：最小时长>0、最大间隙≥0、分析帧率>0")
        self.min_segment_sec = float(min_segment_sec)
        self.max_gap_sec = float(max_gap_sec)
        self.analysis_fps = float(analysis_fps)
        self.min_motion = float(min_motion)
        self.min_presence_ratio = float(min_presence_ratio)
        self.analysis_width = int(analysis_width)
        self.observations: list[FrameObservation] = []
        self.threshold: float = self.min_motion

    def analyze(self, video_path: Path, detector: Optional[Detector] = None) -> tuple[VideoMetadata, list[Segment]]:
        video_path = Path(video_path)
        metadata = read_video_metadata(video_path)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频：{video_path}")

        sample_step = max(1, int(round(metadata.fps / self.analysis_fps)))
        subtractor = cv2.createBackgroundSubtractorMOG2(
            history=max(100, int(metadata.fps * 5)),
            varThreshold=24,
            detectShadows=False,
        )
        prev_gray: Optional[np.ndarray] = None
        observations: list[FrameObservation] = []
        frame_index = 0
        work_width = min(metadata.width, self.analysis_width)
        scale = work_width / float(metadata.width)
        work_height = max(1, int(round(metadata.height * scale)))
        min_blob_pixels = max(64, int(work_width * work_height * 0.001))

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            work_frame = frame
            if metadata.width > self.analysis_width:
                work_frame = cv2.resize(frame, (work_width, work_height), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(work_frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            foreground = subtractor.apply(work_frame)
            if prev_gray is None:
                frame_diff = None
                full_energy = 0.0
            else:
                frame_diff = cv2.absdiff(prev_gray, gray)
                mean_change = float(np.mean(frame_diff)) / 255.0
                motion_pixels = float(np.count_nonzero(frame_diff >= 12)) / frame_diff.size
                full_energy = 0.5 * mean_change + 0.5 * motion_pixels
            prev_gray = gray

            if frame_index % sample_step == 0:
                if detector is not None:
                    bbox = detector(frame)
                    presence = _valid_bbox(bbox, metadata.width, metadata.height)
                    if bbox is not None:
                        x, y, w, h = bbox
                        # Convert a full-resolution detector box to the small
                        # analysis image used for temporal signals.
                        bbox_for_energy = (
                            int(round(x * scale)),
                            int(round(y * scale)),
                            max(1, int(round(w * scale))),
                            max(1, int(round(h * scale))),
                        )
                    else:
                        bbox_for_energy = None
                else:
                    bbox = _largest_foreground_bbox(foreground, min_blob_pixels)
                    presence = _valid_bbox(bbox, work_width, work_height)
                    bbox_for_energy = bbox

                energy = full_energy
                if frame_diff is not None and bbox_for_energy is not None:
                    x, y, w, h = bbox_for_energy
                    pad_x, pad_y = int(0.12 * w), int(0.08 * h)
                    x1 = max(0, x - pad_x)
                    y1 = max(0, y - pad_y)
                    x2 = min(work_width, x + w + pad_x)
                    y2 = min(work_height, y + h + pad_y)
                    roi = frame_diff[y1:y2, x1:x2]
                    if roi.size:
                        roi_change = float(np.mean(roi)) / 255.0
                        roi_motion = float(np.count_nonzero(roi >= 12)) / roi.size
                        # Person-region motion is more informative than a
                        # full 4K frame dominated by a static background.
                        energy = 0.7 * roi_change + 0.3 * roi_motion
                observations.append(
                    FrameObservation(
                        frame_index=frame_index,
                        time_sec=frame_index / metadata.fps,
                        motion_energy=energy,
                        presence=presence,
                        score=0.0,
                        bbox=bbox,
                    )
                )
            frame_index += 1
        cap.release()

        if len(observations) < 2:
            self.observations = observations
            return metadata, []

        energies = np.asarray([o.motion_energy for o in observations], dtype=np.float32)
        # The lower quartile estimates the idle/background level.  IQR makes
        # the threshold adapt to camera resolution and compression noise.
        q25, q75 = np.percentile(energies, [25, 75])
        threshold = max(self.min_motion, float(q25 + 0.15 * (q75 - q25)))
        self.threshold = threshold

        any_presence = any(o.presence for o in observations)
        active = np.asarray(
            [o.motion_energy >= threshold and (o.presence if any_presence else True) for o in observations],
            dtype=bool,
        )
        sample_period = sample_step / metadata.fps
        max_gap_samples = max(0, int(round(self.max_gap_sec / sample_period)))
        min_run_samples = max(1, int(math.ceil(self.min_segment_sec / sample_period)))
        active = _fill_short_gaps(active, max_gap_samples)
        active = _remove_short_runs(active, min_run_samples)

        updated: list[FrameObservation] = []
        for obs, is_active in zip(observations, active):
            normalized_energy = min(1.0, obs.motion_energy / max(threshold * 2.0, 1e-6))
            score = normalized_energy * (1.0 if obs.presence or not any_presence else 0.0)
            updated.append(FrameObservation(**{**asdict(obs), "score": float(score if is_active else 0.0)}))
        self.observations = updated

        segments: list[Segment] = []
        for run_start, run_end in _runs(active):
            first = observations[run_start]
            last = observations[run_end - 1]
            start_frame = first.frame_index
            end_frame = min(metadata.frame_count, last.frame_index + sample_step)
            run_obs = updated[run_start:run_end]
            presence_ratio = float(np.mean([o.presence for o in run_obs]))
            activity_ratio = float(np.mean([o.motion_energy >= threshold for o in run_obs]))
            if any_presence and presence_ratio < self.min_presence_ratio:
                continue
            confidence = float(np.mean([o.score for o in run_obs]))
            segments.append(
                Segment(
                    index=len(segments) + 1,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    fps=metadata.fps,
                    presence_ratio=presence_ratio,
                    activity_ratio=activity_ratio,
                    confidence=confidence,
                )
            )
        return metadata, segments

    def write_analysis_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["frame_index", "time_sec", "motion_energy", "presence", "score", "bbox"],
            )
            writer.writeheader()
            for obs in self.observations:
                row = asdict(obs)
                row["bbox"] = "" if obs.bbox is None else ",".join(map(str, obs.bbox))
                writer.writerow(row)


def _open_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    for codec in ("mp4v", "avc1"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            return writer
        writer.release()
    raise RuntimeError("当前OpenCV无法创建MP4视频写入器，请安装带FFmpeg支持的opencv-python")


def write_video_segments(video_path: Path, output_dir: Path, segments: Sequence[Segment]) -> list[Path]:
    """Write each half-open segment as an MP4 clip, preserving source FPS."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = read_video_metadata(Path(video_path))
    output_paths: list[Path] = []
    for segment in segments:
        output_path = output_dir / f"segment_{segment.index:03d}.mp4"
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, segment.start_frame)
        writer: Optional[cv2.VideoWriter] = None
        frame_idx = segment.start_frame
        try:
            while frame_idx < segment.end_frame:
                ok, frame = cap.read()
                if not ok:
                    break
                if writer is None:
                    writer = _open_writer(output_path, metadata.fps, (frame.shape[1], frame.shape[0]))
                writer.write(frame)
                frame_idx += 1
        finally:
            cap.release()
            if writer is not None:
                writer.release()
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"片段写入失败：{output_path}")
        output_paths.append(output_path)
    return output_paths
