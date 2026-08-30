"""Convert GVHMR SMPL-X parameters into the frozen CARE-PD input contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from app.model_runtime import axis_angle_to_matrix, matrix_to_rotation_6d


TARGET_FPS = 30.0
WINDOW_FRAMES = 60
WINDOW_STRIDE = 30


def window_starts(length: int) -> list[int]:
    if length < WINDOW_FRAMES:
        return []
    starts = list(range(0, length - WINDOW_FRAMES + 1, WINDOW_STRIDE))
    tail = length - WINDOW_FRAMES
    if starts[-1] != tail:
        starts.append(tail)
    return starts


def load_gvhmr_windows(path: Path) -> tuple[np.ndarray, dict[str, object]]:
    """Return float32 ``[B,25,6,60]`` windows from a GVHMR SMPL-X export.

    GVHMR exports the root plus 21 SMPL-X body joints. CARE-PD uses the SMPL
    24-joint body layout; the two terminal hand joints are therefore filled
    with identity rotations. They are not inferred or fabricated measurements.
    """
    with np.load(path, allow_pickle=False) as payload:
        required = {"global_orient", "body_pose", "transl", "fps"}
        missing = required - set(payload.files)
        if missing:
            raise ValueError(f"GVHMR parameter file is missing fields: {sorted(missing)}")
        global_orient = np.asarray(payload["global_orient"], dtype=np.float32)
        body_pose = np.asarray(payload["body_pose"], dtype=np.float32)
        translation = np.asarray(payload["transl"], dtype=np.float32)
        fps = float(np.asarray(payload["fps"]).reshape(()))

    if global_orient.ndim != 2 or global_orient.shape[1] != 3:
        raise ValueError("global_orient must have shape [frames,3]")
    if body_pose.ndim != 2 or body_pose.shape[1] < 63:
        raise ValueError("body_pose must contain the 21 SMPL-X body joints")
    if translation.shape != global_orient.shape:
        raise ValueError("transl must have shape [frames,3]")
    if not np.isfinite(global_orient).all() or not np.isfinite(body_pose).all() or not np.isfinite(translation).all():
        raise ValueError("GVHMR parameters contain NaN or Inf")
    if abs(fps - TARGET_FPS) > 0.05:
        raise ValueError(f"GVHMR output must be 30 FPS, got {fps:g}")

    frame_count = len(global_orient)
    starts = window_starts(frame_count)
    if not starts:
        raise ValueError("At least 60 GVHMR frames are required for MotionCLIP")

    body = body_pose[:, :63].reshape(frame_count, 21, 3)
    neutral_hands = np.zeros((frame_count, 2, 3), dtype=np.float32)
    axis_angle = np.concatenate((global_orient[:, None, :], body, neutral_hands), axis=1)
    with torch.inference_mode():
        rotations = axis_angle_to_matrix(torch.from_numpy(axis_angle))
        rot6d = matrix_to_rotation_6d(rotations).cpu().numpy().astype(np.float32)

    windows = []
    for start in starts:
        stop = start + WINDOW_FRAMES
        translation6d = np.zeros((WINDOW_FRAMES, 1, 6), dtype=np.float32)
        translation6d[:, 0, :3] = translation[start:stop] - translation[start]
        motion = np.concatenate((rot6d[start:stop], translation6d), axis=1)
        windows.append(np.transpose(motion, (1, 2, 0)).copy())

    result = np.stack(windows).astype(np.float32, copy=False)
    if result.shape[1:] != (25, 6, 60) or not np.isfinite(result).all():
        raise ValueError(f"Unexpected MotionCLIP tensor shape: {result.shape}")
    return result, {
        "input_adapter": "gvhmr_smplx_to_carepd_smpl_v1",
        "source_fps": fps,
        "source_frames": frame_count,
        "window_frames": WINDOW_FRAMES,
        "window_stride": WINDOW_STRIDE,
        "window_count": len(starts),
        "neutral_hand_joints": [22, 23],
    }
