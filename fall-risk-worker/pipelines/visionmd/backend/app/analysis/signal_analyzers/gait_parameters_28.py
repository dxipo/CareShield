"""Twenty-eight gait parameters computed from pure VisionMD-Gait outputs.

Inputs are MeTRAbs ``mpi_inf_3dhp_17`` camera-coordinate joints in millimetres
and VisionMD Gait Transformer heel-strike/toe-off frame indices.  No SMPL or
GVHMR data are required.
"""

from __future__ import annotations

import numpy as np


def _finite(values):
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values)]


def _mean(values):
    values = _finite(values)
    return float(np.mean(values)) if len(values) else None


def _sd(values):
    values = _finite(values)
    return float(np.std(values, ddof=1)) if len(values) > 1 else None


def _cv(values):
    mean, sd = _mean(values), _sd(values)
    return float(100.0 * sd / mean) if mean not in (None, 0) and sd is not None else None


def _symmetry(left, right):
    left, right = _mean(left), _mean(right)
    if left is None or right is None or left + right == 0:
        return None
    return float(100.0 * abs(left - right) / (0.5 * (left + right)))


def _angle(a, b, c):
    u, v = a - b, c - b
    denominator = np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1)
    cosine = np.sum(u * v, axis=-1) / np.maximum(denominator, 1e-9)
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _next_after(events, frame, before=None):
    events = np.asarray(events, dtype=int)
    events = events[events > frame]
    if before is not None:
        events = events[events < before]
    return int(events[0]) if len(events) else None


def _phase_durations(starts, ends, fps):
    durations = []
    for start in np.asarray(starts, dtype=int):
        end = _next_after(ends, int(start))
        if end is not None:
            durations.append((end - start) / fps)
    return np.asarray(durations, dtype=float)


def _double_support(lhs, rhs, lto, rto, fps):
    strikes = sorted([(int(f), "left") for f in lhs] + [(int(f), "right") for f in rhs])
    components = []
    for index, (frame, side) in enumerate(strikes):
        next_strike = strikes[index + 1][0] if index + 1 < len(strikes) else None
        toe_off = _next_after(rto if side == "left" else lto, frame, next_strike)
        if toe_off is not None:
            components.append((frame, (toe_off - frame) / fps))
    cycles = []
    for same_side in (np.asarray(lhs, dtype=int), np.asarray(rhs, dtype=int)):
        for start, end in zip(same_side[:-1], same_side[1:]):
            parts = [duration for frame, duration in components if start <= frame < end]
            if len(parts) >= 2:
                cycles.append(sum(parts[:2]))
    return np.asarray(cycles, dtype=float)


def _contacts(length, down, up):
    contact = np.zeros(length, dtype=bool)
    changes = sorted([(int(f), True) for f in down] + [(int(f), False) for f in up])
    if not changes:
        return contact
    state = changes[0][1] is False
    cursor = 0
    for frame, new_state in changes:
        frame = int(np.clip(frame, 0, length))
        contact[cursor:frame] = state
        state, cursor = new_state, frame
    contact[cursor:] = state
    return contact


def _clearance(ankle_up, heel_strikes):
    values = []
    for start, end in zip(heel_strikes[:-1], heel_strikes[1:]):
        start, end = int(start), int(end)
        if end - start < 2:
            continue
        baseline = 0.5 * (ankle_up[start] + ankle_up[end])
        values.append(max(0.0, float(np.max(ankle_up[start:end + 1]) - baseline)))
    return np.asarray(values, dtype=float)


def _estimated_com(joints, idx):
    pelvis, neck = joints[:, idx["pelv"]], joints[:, idx["neck"]]
    segments = [
        (0.497, 0.5 * (pelvis + neck)),
        (0.081, 0.5 * (neck + joints[:, idx["htop"]])),
    ]
    for prefix in ("l", "r"):
        shoulder, elbow, wrist = (joints[:, idx[prefix + name]] for name in ("sho", "elb", "wri"))
        hip, knee, ankle = (joints[:, idx[prefix + name]] for name in ("hip", "kne", "ank"))
        segments.extend([
            (0.028, 0.5 * (shoulder + elbow)),
            (0.016, 0.5 * (elbow + wrist)),
            (0.006, wrist),
            (0.100, 0.5 * (hip + knee)),
            (0.0465, 0.5 * (knee + ankle)),
            (0.0145, ankle),  # MeTRAbs-17 has no toe; ankle is the foot proxy.
        ])
    return sum(mass * center for mass, center in segments)


def calculate_gait_parameters_28(gait_events, poses_3d, fps, joint_order):
    """Return exactly 28 video-level parameters from pure VisionMD outputs."""
    poses = np.asarray(poses_3d, dtype=float) / 1000.0
    if poses.ndim != 3 or poses.shape[2] != 3:
        raise ValueError(f"Expected poses_3d shaped [frames, joints, 3], found {poses.shape}")
    fps = float(fps)
    idx = {str(name): i for i, name in enumerate(joint_order)}
    required = {"htop", "neck", "rsho", "relb", "rwri", "lsho", "lelb", "lwri",
                "rhip", "rkne", "rank", "lhip", "lkne", "lank", "pelv"}
    missing = required.difference(idx)
    if missing:
        raise ValueError(f"Missing MeTRAbs joints: {sorted(missing)}")

    def event(name):
        values = np.unique(np.rint(gait_events.get(name, [])).astype(int))
        return values[(values >= 0) & (values < len(poses))]

    lhs, rhs = event("left_down"), event("right_down")
    lto, rto = event("left_up"), event("right_up")
    strikes = sorted([(int(f), "left") for f in lhs] + [(int(f), "right") for f in rhs])

    pelvis = poses[:, idx["pelv"]]
    left_ankle, right_ankle = poses[:, idx["lank"]], poses[:, idx["rank"]]
    step_times, step_lengths, step_widths, step_sides = [], [], [], []
    for (previous, previous_side), (frame, side) in zip(strikes[:-1], strikes[1:]):
        interval = (frame - previous) / fps
        if side == previous_side or not 0.20 <= interval <= 2.0:
            continue
        step_times.append(interval)
        step_lengths.append(abs(pelvis[frame, 2] - pelvis[previous, 2]))
        step_widths.append(abs(left_ankle[frame, 0] - right_ankle[frame, 0]))
        step_sides.append(side)
    step_times = np.asarray(step_times, dtype=float)
    step_lengths = np.asarray(step_lengths, dtype=float)
    step_widths = np.asarray(step_widths, dtype=float)
    step_sides = np.asarray(step_sides)
    left_steps, right_steps = step_times[step_sides == "left"], step_times[step_sides == "right"]

    stride_times = np.concatenate([
        np.diff(lhs) / fps if len(lhs) > 1 else np.array([], dtype=float),
        np.diff(rhs) / fps if len(rhs) > 1 else np.array([], dtype=float),
    ])
    stance_times = np.concatenate([_phase_durations(lhs, lto, fps), _phase_durations(rhs, rto, fps)])
    swing_times = np.concatenate([_phase_durations(lto, lhs, fps), _phase_durations(rto, rhs, fps)])
    double_support_times = _double_support(lhs, rhs, lto, rto, fps)

    first_hs = min([f for f, _ in strikes], default=0)
    last_hs = max([f for f, _ in strikes], default=len(poses) - 1)
    active = slice(first_hs, last_hs + 1)
    left_wrist = poses[:, idx["lwri"]] - pelvis
    right_wrist = poses[:, idx["rwri"]] - pelvis
    arm_swing = 0.5 * (np.ptp(left_wrist[active, 2]) + np.ptp(right_wrist[active, 2]))
    left_clearance = _clearance(-left_ankle[:, 1], lhs)
    right_clearance = _clearance(-right_ankle[:, 1], rhs)

    shoulder_mid = 0.5 * (poses[:, idx["lsho"]] + poses[:, idx["rsho"]])
    trunk = shoulder_mid - pelvis
    up = np.zeros_like(trunk)
    up[:, 1] = -1.0  # MeTRAbs camera Y points down.
    trunk_lean = _angle(pelvis + up, pelvis, shoulder_mid)
    hip_left = 180.0 - _angle(shoulder_mid, poses[:, idx["lhip"]], poses[:, idx["lkne"]])
    hip_right = 180.0 - _angle(shoulder_mid, poses[:, idx["rhip"]], poses[:, idx["rkne"]])
    knee_left = 180.0 - _angle(poses[:, idx["lhip"]], poses[:, idx["lkne"]], left_ankle)
    knee_right = 180.0 - _angle(poses[:, idx["rhip"]], poses[:, idx["rkne"]], right_ankle)

    ecom = _estimated_com(poses, idx)
    hip_width = np.linalg.norm(poses[:, idx["lhip"]] - poses[:, idx["rhip"]], axis=1)
    ground_y = np.maximum(left_ankle[:, 1], right_ankle[:, 1])
    pendulum_length = np.maximum(ground_y - ecom[:, 1], 0.35)
    omega0 = np.sqrt(9.80665 / pendulum_length)
    xcom_lateral = ecom[:, 0] + np.gradient(ecom[:, 0]) * fps / omega0
    left_contact, right_contact = _contacts(len(poses), lhs, lto), _contacts(len(poses), rhs, rto)
    half_foot_width = np.maximum(0.02, 0.12 * hip_width)
    lower, upper = np.full(len(poses), np.nan), np.full(len(poses), np.nan)
    for frame in range(len(poses)):
        centers = []
        if left_contact[frame]:
            centers.append(left_ankle[frame, 0])
        if right_contact[frame]:
            centers.append(right_ankle[frame, 0])
        if centers:
            lower[frame] = min(centers) - half_foot_width[frame]
            upper[frame] = max(centers) + half_foot_width[frame]
    emos = np.minimum(xcom_lateral - lower, upper - xcom_lateral)
    valid_emos = _finite(emos[active])
    ecom_active, xcom_active = ecom[active, 0], xcom_lateral[active]

    step_time = _mean(step_times)
    step_length = _mean(step_lengths)
    parameters = {
        "cadence_spm": 60.0 / step_time if step_time else None,
        "step_time_s": step_time,
        "stride_time_s": _mean(stride_times),
        "stance_time_s": _mean(stance_times),
        "swing_time_s": _mean(swing_times),
        "double_support_time_s": _mean(double_support_times),
        "step_length_m": step_length,
        "gait_speed_m_s": step_length / step_time if step_length is not None and step_time else None,
        "step_width_m": _mean(step_widths),
        "arm_swing_amplitude_m": float(arm_swing) if np.isfinite(arm_swing) else None,
        "left_foot_clearance_m": _mean(left_clearance),
        "right_foot_clearance_m": _mean(right_clearance),
        "step_time_sd_s": _sd(step_times),
        "stride_time_sd_s": _sd(stride_times),
        "step_time_cv_percent": _cv(step_times),
        "stride_time_cv_percent": _cv(stride_times),
        "step_length_cv_percent": _cv(step_lengths),
        "step_width_cv_percent": _cv(step_widths),
        "step_time_symmetry_percent": _symmetry(left_steps, right_steps),
        "trunk_lean_deg": _mean(trunk_lean[active]),
        "hip_asymmetry_deg": _mean(np.abs(hip_left[active] - hip_right[active])),
        "knee_asymmetry_deg": _mean(np.abs(knee_left[active] - knee_right[active])),
        "hip_knee_asymmetry_deg": _mean(0.5 * (np.abs(hip_left[active] - hip_right[active]) +
                                                np.abs(knee_left[active] - knee_right[active]))),
        "ecom_lateral_rms_m": float(np.sqrt(np.mean((ecom_active - np.mean(ecom_active)) ** 2))),
        "xcom_lateral_rms_m": float(np.sqrt(np.mean((xcom_active - np.mean(xcom_active)) ** 2))),
        "emos_min_m": float(np.min(valid_emos)) if len(valid_emos) else None,
        "emos_mean_m": float(np.mean(valid_emos)) if len(valid_emos) else None,
        "emos_normalized_by_hip_width": (float(np.mean(valid_emos) / np.mean(hip_width[active]))
                                          if len(valid_emos) and np.mean(hip_width[active]) else None),
    }
    if len(parameters) != 28:
        raise RuntimeError(f"Expected 28 parameters, created {len(parameters)}")
    return parameters
