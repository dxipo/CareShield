"""Standalone pure VisionMD-Gait pipeline: RGB -> MeTRAbs -> events -> 28 parameters."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.analysis.models.gait_transformer.gait_phase_kalman import (  # noqa: E402
    gait_kalman_smoother,
    get_event_times,
)
from app.analysis.models.gait_transformer.gait_phase_transformer_old import (  # noqa: E402
    gait_phase_stride_inference,
    load_default_model,
)
from app.analysis.signal_analyzers.gait_parameters_28 import (  # noqa: E402
    calculate_gait_parameters_28,
)
from segment_selection import select_continuous_segment  # noqa: E402


JOINT_ORDER = np.array([
    "htop", "neck", "rsho", "relb", "rwri", "lsho", "lelb", "lwri",
    "rhip", "rkne", "rank", "lhip", "lkne", "lank", "pelv", "spin", "head",
])
GAIT_ORDER = np.array([
    "pelv", "rhip", "rkne", "rank", "lhip", "lkne", "lank", "spin",
    "neck", "head", "htop", "lsho", "lelb", "lwri", "rsho", "relb", "rwri",
])
SKELETON_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 4), (1, 5), (5, 6), (6, 7),
    (1, 16), (16, 15), (15, 14), (14, 8), (8, 9), (9, 10),
    (14, 11), (11, 12), (12, 13), (8, 11),
)


class InsufficientPoseError(RuntimeError):
    """The recording does not contain enough observable full-body pose data."""


def _load_metrabs(model_dir: Path, model_url: str):
    if model_dir.is_dir():
        print(f"Loading MeTRAbs from {model_dir}")
        return hub.load(str(model_dir))
    print(f"Downloading MeTRAbs from {model_url}")
    model = hub.load(model_url)
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    tf.saved_model.save(model, str(model_dir))
    return hub.load(str(model_dir))


def _interpolate_missing(values: np.ndarray) -> np.ndarray:
    output = values.copy()
    frames = np.arange(len(output))
    for joint in range(output.shape[1]):
        for coordinate in range(output.shape[2]):
            signal = output[:, joint, coordinate]
            valid = np.isfinite(signal)
            if valid.any():
                output[:, joint, coordinate] = np.interp(frames, frames[valid], signal[valid])
    if not np.isfinite(output).all():
        raise InsufficientPoseError(
            "MeTRAbs did not detect a valid person in enough frames to interpolate the pose"
        )
    return output


def _maximum_false_run(valid: np.ndarray) -> int:
    maximum = current = 0
    for item in valid:
        current = 0 if item else current + 1
        maximum = max(maximum, current)
    return maximum


def extract_poses(video_path: Path, detector, batch_size: int):
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    poses3d, poses2d, batch = [], [], []

    def infer(frames):
        images = tf.convert_to_tensor(np.stack(frames), dtype=tf.uint8)
        prediction = detector.detect_poses_batched(
            images=images,
            skeleton="mpi_inf_3dhp_17",
            detector_flip_aug=True,
            detector_threshold=0.2,
        )
        for frame_index in range(len(frames)):
            if prediction["poses3d"][frame_index].shape[0] == 0:
                poses3d.append(np.full((17, 3), np.nan))
                poses2d.append(np.full((17, 2), np.nan))
            else:
                poses3d.append(prediction["poses3d"][frame_index, 0].numpy())
                poses2d.append(prediction["poses2d"][frame_index, 0].numpy())

    while True:
        ok, frame_bgr = capture.read()
        if not ok:
            break
        batch.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        if len(batch) == batch_size:
            infer(batch)
            batch = []
    if batch:
        infer(batch)
    capture.release()
    if not poses3d:
        raise RuntimeError("Video contains no readable frames")
    raw_3d = np.asarray(poses3d)
    raw_2d = np.asarray(poses2d)
    valid = np.isfinite(raw_3d).all(axis=(1, 2)) & np.isfinite(raw_2d).all(axis=(1, 2))
    within_frame = valid & (
        (raw_2d[..., 0] >= 0).all(axis=1)
        & (raw_2d[..., 0] < width).all(axis=1)
        & (raw_2d[..., 1] >= 0).all(axis=1)
        & (raw_2d[..., 1] < height).all(axis=1)
    )
    return raw_3d, raw_2d, valid, within_frame, fps


def create_analysis_clip(
    video_path: Path,
    output: Path,
    start_frame: int,
    end_frame: int,
) -> None:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video_path),
            "-vf", f"trim=start_frame={start_frame}:end_frame={end_frame},setpts=PTS-STARTPTS",
            "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(output),
        ],
        check=True,
    )


def render_overlay(video_path: Path, poses2d: np.ndarray, output: Path, fps: float) -> None:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FileNotFoundError(f"Cannot open video for overlay: {video_path}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    temporary = output.with_suffix(".mp4v.mp4")
    writer = cv2.VideoWriter(
        str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Cannot create VisionMD overlay video")
    frame_index = 0
    while frame_index < len(poses2d):
        ok, frame = capture.read()
        if not ok:
            break
        points = poses2d[frame_index]
        for first, second in SKELETON_EDGES:
            p1 = tuple(np.rint(points[first]).astype(int))
            p2 = tuple(np.rint(points[second]).astype(int))
            cv2.line(frame, p1, p2, (76, 220, 176), 3, cv2.LINE_AA)
        for point in points:
            center = tuple(np.rint(point).astype(int))
            cv2.circle(frame, center, 4, (31, 91, 255), -1, cv2.LINE_AA)
        writer.write(frame)
        frame_index += 1
    capture.release()
    writer.release()
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(temporary), "-an", "-c:v", "libx264", "-preset", "fast",
            "-crf", "20", "-pix_fmt", "yuv420p", str(output),
        ],
        check=True,
    )
    temporary.unlink(missing_ok=True)


def infer_events(poses3d_mm: np.ndarray, height_cm: float):
    reorder = np.array([np.where(JOINT_ORDER == name)[0][0] for name in GAIT_ORDER])
    keypoints = poses3d_mm[:, reorder] / 1000.0
    keypoints = keypoints - np.mean(keypoints, axis=1, keepdims=True)
    keypoints = keypoints[:, :, [0, 2, 1]]
    keypoints[:, :, 2] *= -1.0
    transformer = load_default_model(pos_divider=2)
    phases, stride_signals = gait_phase_stride_inference(
        keypoints,
        np.asarray(height_cm * 10.0, dtype=float),
        transformer,
        120,
    )
    phase_ordered = np.take(phases, [0, 4, 1, 5, 2, 6, 3, 7], axis=-1)
    state, _, _ = gait_kalman_smoother(phase_ordered)
    events = get_event_times(state, np.arange(len(state)))
    events = {name: np.asarray(values, dtype=float) for name, values in events.items()}
    return events, phases, stride_signals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--height-cm", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--metrabs-url", default="https://bit.ly/metrabs_s")
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model_dir = Path(
        os.getenv(
            "VISIONMD_METRABS_MODEL_DIR",
            str(BACKEND / "app" / "analysis" / "models" / "metrabs_local_s"),
        )
    )
    detector = _load_metrabs(model_dir, args.metrabs_url)
    raw_3d, raw_2d, valid, within_frame, fps = extract_poses(
        args.video.resolve(), detector, args.batch_size
    )
    try:
        segment = select_continuous_segment(valid, fps)
    except ValueError as exc:
        raise InsufficientPoseError(str(exc)) from exc
    selected_valid = valid[segment.start:segment.end]
    selected_within_frame = within_frame[segment.start:segment.end]
    poses3d = _interpolate_missing(raw_3d[segment.start:segment.end])
    poses2d = _interpolate_missing(raw_2d[segment.start:segment.end])
    maximum_missing_gap = _maximum_false_run(selected_valid)
    original_duration = float(len(raw_3d) / fps) if fps > 0 else None
    selected_duration = float(segment.frame_count / fps) if fps > 0 else None
    quality = {
        "pose_valid_ratio": float(np.mean(selected_valid)),
        "full_body_visible_ratio": float(np.mean(selected_within_frame)),
        "interpolated_frame_ratio": float(1.0 - np.mean(selected_valid)),
        "maximum_missing_gap_frames": maximum_missing_gap,
        "maximum_missing_gap_seconds": (
            float(maximum_missing_gap / fps) if fps > 0 else None
        ),
        "video_duration_seconds": selected_duration,
        "original_video_duration_seconds": original_duration,
        "selected_start_seconds": float(segment.start / fps) if fps > 0 else None,
        "selected_end_seconds": float(segment.end / fps) if fps > 0 else None,
        "discarded_duration_seconds": (
            float(original_duration - selected_duration)
            if original_duration is not None and selected_duration is not None
            else None
        ),
    }
    analysis_clip = output / "analysis_clip.mp4"
    create_analysis_clip(args.video.resolve(), analysis_clip, segment.start, segment.end)
    events, phases, stride_signals = infer_events(poses3d, args.height_cm)
    parameters = calculate_gait_parameters_28(events, poses3d, fps, JOINT_ORDER)
    render_overlay(analysis_clip, poses2d, output / "visionmd_overlay.mp4", fps)

    np.savez_compressed(
        output / "visionmd_poses.npz",
        poses3d_mm=poses3d.astype(np.float32),
        poses2d_px=poses2d.astype(np.float32),
        joint_order=JOINT_ORDER,
        fps=np.float32(fps),
        coordinate_system="MeTRAbs camera: X-right,Y-down,Z-forward,millimetres",
    )
    np.savez_compressed(
        output / "visionmd_signals.npz",
        phases=phases.astype(np.float32),
        stride_signals=stride_signals.astype(np.float32),
    )
    event_json = {name: values.tolist() for name, values in events.items()}
    (output / "gait_events.json").write_text(
        json.dumps(event_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result = {
        "pipeline": "pure_visionmd_gait",
        "video": str(args.video.resolve()),
        "fps": fps,
        "height_cm": args.height_cm,
        "analysis_clip": "analysis_clip.mp4",
        "quality": quality,
        "gait_parameters_28": parameters,
    }
    (output / "gait_parameters_28.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except InsufficientPoseError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(20) from None
