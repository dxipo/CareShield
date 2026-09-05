"""Run GaitTransformer event decoding and calculate all gait parameters."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import numpy as np

from gaitkit.core.joints import H36M_17
from gaitkit.core.types import GaitEvents
from gaitkit.events.visionmd import VisionMDEventDetector, visionmd_preprocess
from gaitkit.io.trajectory_io import load_trajectory
from gaitkit.metrics.registry import CANONICAL_METRICS, metric_manifest
from gaitkit.pipeline import GaitPipeline
from gaitkit.preprocess.temporal import resample_trajectory


def _events_from_result(payload: dict[str, Any]) -> GaitEvents:
    events = payload["events"]
    return GaitEvents(
        left_down=np.asarray(events["left_heel_strike_s"], dtype=float),
        right_down=np.asarray(events["right_heel_strike_s"], dtype=float),
        left_up=np.asarray(events["left_toe_off_s"], dtype=float),
        right_up=np.asarray(events["right_toe_off_s"], dtype=float),
        detector=str(events["detector"]),
        metadata=dict(events.get("metadata", {})),
    )


def _write_events(path: Path, events: GaitEvents) -> None:
    rows: list[tuple[str, str, float]] = []
    for side, name, values in (
        ("left", "heel_strike", events.left_down),
        ("right", "heel_strike", events.right_down),
        ("left", "toe_off", events.left_up),
        ("right", "toe_off", events.right_up),
    ):
        rows.extend((side, name, float(value)) for value in values)
    rows.sort(key=lambda item: item[2])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(("side", "event", "time_s"))
        writer.writerows(rows)


def _write_metrics(path: Path, result: dict) -> None:
    definitions = {item["name"]: item for item in metric_manifest()}
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = (
            "index", "name", "cn_name", "value", "unit", "group", "tier",
            "formula",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, name in enumerate(CANONICAL_METRICS, 1):
            definition = definitions[name]
            writer.writerow({
                "index": index,
                "name": name,
                "cn_name": definition["cn_name"],
                "value": result["metrics"].get(name),
                "unit": definition["unit"],
                "group": definition["group"],
                "tier": definition["tier"],
                "formula": definition["formula"],
            })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory", required=True)
    parser.add_argument("--height-mm", required=True, type=float)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gait-transformer-root", required=True)
    parser.add_argument("--window-frames", type=int, default=60)
    parser.add_argument("--use-xla", action="store_true")
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    transformer_root = Path(args.gait_transformer_root).resolve()
    if not transformer_root.is_dir():
        raise FileNotFoundError("GaitTransformer repository is unavailable")
    sys.path.insert(0, str(transformer_root))

    trajectory = load_trajectory(args.trajectory)
    sampled = resample_trajectory(trajectory, 30.0) if abs(trajectory.fps - 30.0) > 0.1 else trajectory
    points = np.stack([sampled.joints[name] for name in H36M_17], axis=1)
    standardized = visionmd_preprocess(points, sampled.up_axis).astype(np.float32)
    np.savez_compressed(
        output / "gait_transformer_input_h36m17.npz",
        schema_version=np.asarray("gaitkit-gait-transformer-input-1.0"),
        keypoints=standardized,
        time_s=sampled.time_s.astype(np.float64),
        joint_names=np.asarray(H36M_17, dtype="U"),
        fps=np.asarray(30.0, dtype=np.float32),
        normalization=np.asarray("frame_centroid_centered; axes=(x,z,-y) from Y-up source"),
    )

    detector = VisionMDEventDetector(target_fps=30.0, window_frames=args.window_frames, use_xla=args.use_xla)
    result = GaitPipeline(event_detector=detector).analyse(sampled, args.height_mm).to_dict()
    events = _events_from_result(result)
    _write_events(output / "gait_events.csv", events)
    _write_metrics(output / "gait_metrics_28.csv", result)
    print("28 gait parameters saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
