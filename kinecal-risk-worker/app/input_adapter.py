"""Adapt CareShield GVHMR world joints to the KINECAL H36M-17 contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np


TARGET_JOINTS = (
    "pelvis", "right_hip", "right_knee", "right_ankle",
    "left_hip", "left_knee", "left_ankle", "spine", "thorax",
    "neck", "head", "left_shoulder", "left_elbow", "left_wrist",
    "right_shoulder", "right_elbow", "right_wrist",
)


def _interpolate_missing(joints: np.ndarray) -> np.ndarray:
    value = joints.astype(np.float32, copy=True)
    for joint in range(value.shape[1]):
        for coordinate in range(value.shape[2]):
            column = value[:, joint, coordinate]
            valid = np.isfinite(column)
            if valid.all():
                continue
            if not valid.any():
                raise ValueError("A required joint is missing for the complete sequence")
            column[~valid] = np.interp(
                np.flatnonzero(~valid), np.flatnonzero(valid), column[valid]
            )
    return value


def _uniform_sample(joints: np.ndarray, frames: int = 120) -> np.ndarray:
    if len(joints) < 2:
        raise ValueError("At least two skeleton frames are required")
    indices = np.linspace(0, len(joints) - 1, frames).round().astype(np.int64)
    return joints[indices]


def _to_kinect_axes(joints: np.ndarray) -> np.ndarray:
    # GVHMR export: X-forward, Y-left, Z-up. Kinect training data uses
    # X-right, Y-up, Z-depth, so preserve handed body orientation explicitly.
    return np.stack((-joints[..., 1], joints[..., 2], joints[..., 0]), axis=-1)


def adapt_world_skeleton(
    joints: np.ndarray,
    joint_names: list[str],
    *,
    clip_frames: int = 120,
) -> np.ndarray:
    if joints.ndim != 3 or joints.shape[-1] != 3:
        raise ValueError("World skeleton must have shape [frames,joints,3]")
    lookup = {name: index for index, name in enumerate(joint_names)}
    required = set(TARGET_JOINTS) - {"thorax"}
    missing = sorted(required - set(lookup))
    if missing:
        raise ValueError("World skeleton is missing required joints")

    selected = []
    for name in TARGET_JOINTS:
        if name == "thorax":
            selected.append(
                (joints[:, lookup["left_shoulder"]] + joints[:, lookup["right_shoulder"]])
                * 0.5
            )
        else:
            selected.append(joints[:, lookup[name]])
    h36m = np.stack(selected, axis=1)
    h36m = _to_kinect_axes(_interpolate_missing(h36m))
    h36m = _uniform_sample(h36m, clip_frames)
    h36m = h36m - h36m[:, :1, :]
    scale = float(np.std(h36m.reshape(-1, 3), axis=0).mean())
    if not np.isfinite(scale) or scale < 1e-6:
        raise ValueError("World skeleton has insufficient motion scale")
    h36m = h36m / scale
    # KINECAL/ST-GCN++ tensor contract: [C,T,V,M].
    return h36m.transpose(2, 0, 1)[..., None].astype(np.float32)


def load_world_skeleton(path: Path) -> tuple[np.ndarray, dict[str, float | int | str]]:
    with np.load(path, allow_pickle=False) as payload:
        joints = np.asarray(payload["joints"], dtype=np.float32)
        names = [str(item) for item in payload["joint_names"].tolist()]
        fps = float(payload["fps"])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("World skeleton FPS is invalid")
    tensor = adapt_world_skeleton(joints, names)
    return tensor, {
        "source_frames": int(len(joints)),
        "source_fps": fps,
        "source_duration_seconds": float(len(joints) / fps),
        "input_adapter": "gvhmr_world21_to_kinecal_h36m17_v1",
    }
