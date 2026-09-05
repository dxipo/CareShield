"""Run GVHMR and regress its global SMPL-X result to a named 3D skeleton."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from gaitkit.io.gvhmr import load_hmr4d_results
from gaitkit.io.trajectory_io import save_trajectory


def _locate_result(root: Path) -> Path:
    candidates = sorted(root.rglob("hmr4d_results.pt"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("GVHMR finished without producing hmr4d_results.pt")
    return candidates[0]


def _run_gvhmr(args: argparse.Namespace, model_root: Path, output: Path) -> Path:
    raw = output / "gvhmr_work"
    raw.mkdir(parents=True, exist_ok=True)
    if args.gvhmr_entry:
        entry = Path(args.gvhmr_entry)
        command = [sys.executable, str(entry), "--video", str(Path(args.video).resolve()), "--output_root", str(raw), "--skip_render"]
        if args.static_camera:
            command.append("--static_cam")
    else:
        entry = Path(__file__).resolve().parents[1] / "adapters" / "gvhmr_headless.py"
        command = [sys.executable, str(entry), "--video", str(Path(args.video).resolve()), "--output-root", str(raw)]
        if args.static_camera:
            command.append("--static-camera")
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(model_root) + (os.pathsep + existing if existing else "")
    subprocess.run(command, cwd=model_root, env=environment, check=True)
    return _locate_result(raw)


def _export_smpl_parameters(result_path: Path, output_path: Path, expected_frames: int | None) -> None:
    import torch

    prediction = torch.load(result_path, map_location="cpu")
    errors: list[str] = []
    if not isinstance(prediction, dict) or "smpl_params_global" not in prediction:
        raise ValueError("GVHMR result does not contain smpl_params_global")
    params = prediction["smpl_params_global"]
    if not isinstance(params, dict):
        raise ValueError("smpl_params_global is not a parameter dictionary")
    required = ("body_pose", "betas", "global_orient", "transl")
    missing = [name for name in required if name not in params]
    if missing:
        errors.append("missing SMPL-X parameters: " + ", ".join(missing))
    arrays: dict[str, np.ndarray] = {}
    finite_ratios: dict[str, float] = {}
    frame_counts: dict[str, int] = {}
    for name, value in params.items():
        if hasattr(value, "detach"):
            array = value.detach().cpu().numpy()
        else:
            array = np.asarray(value)
        if array.dtype.kind not in "biufc":
            continue
        arrays[str(name)] = array
        finite_ratios[str(name)] = float(np.mean(np.isfinite(array)))
        if array.ndim:
            frame_counts[str(name)] = int(array.shape[0])
        if finite_ratios[str(name)] < 1.0:
            errors.append(f"non-finite SMPL-X parameter: {name}")
    reference_frames = frame_counts.get("transl", 0)
    for name in ("body_pose", "global_orient", "transl"):
        if name in frame_counts and frame_counts[name] != reference_frames:
            errors.append(f"SMPL-X frame count mismatch: {name}")
    if expected_frames is not None and abs(reference_frames - expected_frames) > 1:
        errors.append("SMPL-X and video frame counts do not match")
    if "betas" in frame_counts and frame_counts["betas"] not in {1, reference_frames}:
        errors.append("unexpected betas frame count")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        schema_version=np.asarray("gaitkit-smplx-global-1.0"),
        fps=np.asarray(30.0, dtype=np.float32),
        **arrays,
    )
    if errors:
        raise ValueError("; ".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--gvhmr-root", required=True)
    parser.add_argument("--gvhmr-entry")
    parser.add_argument("--static-camera", action="store_true")
    parser.add_argument("--expected-frames", type=int)
    parser.add_argument("--cached-result")
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    model_root = Path(args.gvhmr_root).resolve()
    if not model_root.is_dir():
        raise FileNotFoundError("GVHMR repository is unavailable")
    source_result = Path(args.cached_result).resolve() if args.cached_result else _run_gvhmr(args, model_root, output)
    result_path = output / "hmr4d_results.pt"
    if source_result != result_path:
        shutil.copy2(source_result, result_path)

    _export_smpl_parameters(result_path, output / "smplx_global_params.npz", args.expected_frames)

    trajectory = load_hmr4d_results(
        result_path,
        gvhmr_root=model_root,
        fps=30.0,
        participant="anonymous",
        view="single_view",
    )
    save_trajectory(output / "world_skeleton_21.npz", trajectory)
    print("SMPL-X parameters and world skeleton saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
