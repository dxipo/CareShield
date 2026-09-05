"""Run GaitKit 2.0 on an existing CareShield GVHMR world skeleton.

This adapter deliberately does not invoke GVHMR again.  The assessment worker
owns video selection and GVHMR execution; this process only performs the
30 Hz GaitTransformer event decode and world-coordinate parameter calculation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np


ALGORITHM_ID = "gaitkit-world-gait-parameters"
ALGORITHM_VERSION = "2.0-careshield.1"
METRIC_DEFINITION_VERSION = "gaitkit-metrics-2.0"


def _load_world_skeleton(path: Path):
    from gaitkit.core.types import Trajectory

    with np.load(path, allow_pickle=False) as payload:
        joints = np.asarray(payload["joints"], dtype=np.float64)
        names = [str(value) for value in payload["joint_names"].tolist()]
        fps = float(np.asarray(payload["fps"]).item())
        coordinate_system = str(np.asarray(payload["coordinate_system"]).item())

    if joints.ndim != 3 or joints.shape[2] != 3 or joints.shape[1] != len(names):
        raise ValueError("CareShield world skeleton shape is invalid")
    if len(joints) < 10 or not np.isfinite(joints).all():
        raise ValueError("CareShield world skeleton does not contain a usable trajectory")
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("CareShield world skeleton FPS is invalid")
    if "Z-up" not in coordinate_system or "metres" not in coordinate_system:
        raise ValueError("CareShield world skeleton is not metric Z-up data")

    named = {name: joints[:, index] for index, name in enumerate(names)}
    # The current exporter provides head and an extrapolated head_top rather
    # than separate H36M nose/head points.  The explicit adapter below preserves
    # the 17-node topology without silently changing the stored source file.
    if "nose" not in named and "head" in named:
        named["nose"] = named["head"].copy()
    if "head_top" in named:
        named["head"] = named["head_top"].copy()

    time_s = np.arange(len(joints), dtype=np.float64) / fps
    return Trajectory(
        time_s=time_s,
        joints=named,
        source="CareShield GVHMR world_skeleton_3d.npz",
        world_grounded=True,
        up_axis=2,
        participant="assessment",
        view="camera",
    )


def _json_number(value: object) -> float | None:
    if isinstance(value, (float, int, np.floating, np.integer)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", type=Path, required=True)
    parser.add_argument("--height-cm", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--visionmd-backend",
        type=Path,
        default=Path("/opt/visionmd-app/backend"),
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "vendor"))
    sys.path.insert(0, str(args.visionmd_backend.resolve()))

    from gaitkit.events.visionmd import VisionMDEventDetector
    from gaitkit.metrics import METRIC_REGISTRY, compute_all
    from gaitkit.preprocess.temporal import resample_trajectory

    trajectory = _load_world_skeleton(args.skeleton.resolve())
    sampled = resample_trajectory(trajectory, 30.0) if abs(trajectory.fps - 30.0) > 0.1 else trajectory
    detector = VisionMDEventDetector(target_fps=30.0, window_frames=60)
    events = detector.detect(sampled, args.height_cm * 10.0)
    metrics = compute_all(sampled, events)
    serialised_metrics = {name: _json_number(metrics.get(name)) for name in metrics}
    unavailable = [name for name, value in serialised_metrics.items() if value is None]
    hs_count = events.total_heel_strikes

    result = {
        "schema_version": "2.0",
        "algorithm": {
            "id": ALGORITHM_ID,
            "version": ALGORITHM_VERSION,
            "metric_definition_version": METRIC_DEFINITION_VERSION,
            "event_detector": events.detector,
        },
        "source": {
            "frames": int(len(sampled.time_s)),
            "fps": float(sampled.fps),
            "duration_seconds": float(sampled.duration_s),
            "coordinate_system": "X-forward,Y-left,Z-up,metres",
            "world_grounded": True,
            "joint_adapter": "careshield-world21-to-h36m17-v1",
        },
        "metrics": serialised_metrics,
        "metric_manifest": [
            {
                "name": metric.name,
                "display_name": metric.cn_name,
                "unit": metric.unit,
                "group": metric.group,
                "tier": metric.tier,
                "formula": metric.formula,
            }
            for metric in METRIC_REGISTRY
        ],
        "events": events.to_dict(),
        "quality": {
            "heel_strike_count": hs_count,
            "toe_off_count": int(len(events.left_up) + len(events.right_up)),
            "complete_step_count": max(0, hs_count - 1),
            "available_parameter_count": len(serialised_metrics) - len(unavailable),
            "unavailable_parameters": unavailable,
            "full_parameter_set_available": hs_count >= 6 and not unavailable,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
