"""RGB -> GVHMR SMPL-X/rendered videos -> metric global 3D skeleton."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GVHMR_ROOT = Path(os.getenv("GVHMR_PROJECT_ROOT", "/opt/gvhmr"))
REQUIRED_ASSETS = [
    "inputs/checkpoints/gvhmr/gvhmr_siga24_release.ckpt",
    "inputs/checkpoints/hmr2/epoch=10-step=25000.ckpt",
    "inputs/checkpoints/vitpose/vitpose-h-multi-coco.pth",
    "inputs/checkpoints/yolo/yolov8x.pt",
    "inputs/checkpoints/body_models/smpl/SMPL_NEUTRAL.pkl",
    "inputs/checkpoints/body_models/smplx/SMPLX_NEUTRAL.npz",
]
# Official Google Drive object size. A previous interrupted/resumed download
# produced a larger concatenated ZIP that still passed a plain existence check.
HMR2_CHECKPOINT_SIZE = 2_709_494_041


def _normalize_video(source, destination, fps, start, duration):
    destination.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not available in the GVHMR worker")
    command = [ffmpeg, "-y"]
    if start is not None:
        command += ["-ss", str(start)]
    command += ["-i", str(source)]
    if duration is not None:
        command += ["-t", str(duration)]
    command += [
        "-an", "-vf", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", str(destination),
    ]
    subprocess.run(command, check=True)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--start-seconds", type=float)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--moving-camera", action="store_true",
                        help="Enable camera-motion estimation; default assumes a fixed camera")
    args = parser.parse_args()

    missing = [asset for asset in REQUIRED_ASSETS if not (GVHMR_ROOT / asset).is_file()]
    if missing:
        raise FileNotFoundError("Missing GVHMR assets:\n  " + "\n  ".join(missing))
    hmr2_checkpoint = GVHMR_ROOT / "inputs/checkpoints/hmr2/epoch=10-step=25000.ckpt"
    if hmr2_checkpoint.stat().st_size != HMR2_CHECKPOINT_SIZE:
        raise RuntimeError("HMR2 checkpoint failed the official size integrity check")
    video = args.video.resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    output = args.output.resolve()
    normalized = output / "preprocessed" / "input_30fps.mp4"
    _normalize_video(video, normalized, args.fps, args.start_seconds, args.duration_seconds)

    gvhmr_output = output / "gvhmr"
    hydra_output = f'"{str(gvhmr_output).replace(chr(34), chr(92) + chr(34))}"'
    command = [
        sys.executable,
        str(GVHMR_ROOT / "tools/demo/demo.py"),
        "--video", str(normalized),
        "--output_root", hydra_output,
    ]
    if not args.moving_camera:
        command.append("-s")
    subprocess.run(command, cwd=GVHMR_ROOT, check=True)

    expected = gvhmr_output / normalized.stem / "hmr4d_results.pt"
    if not expected.is_file():
        matches = list(gvhmr_output.rglob("hmr4d_results.pt"))
        if len(matches) != 1:
            raise FileNotFoundError("Cannot uniquely locate GVHMR hmr4d_results.pt")
        expected = matches[0]

    skeleton_output = output / "world_skeleton_3d.npz"
    smplx_output = output / "smplx_global_params.npz"
    subprocess.run([
        sys.executable,
        str(ROOT / "export_world_skeleton.py"),
        "--gvhmr-root", str(GVHMR_ROOT),
        "--input", str(expected),
        "--skeleton-output", str(skeleton_output),
        "--smplx-output", str(smplx_output),
        "--fps", str(args.fps),
    ], cwd=GVHMR_ROOT, check=True)

    render_dir = expected.parent
    manifest = {
        "pipeline": "RGB -> GVHMR -> global SMPL-X -> metric 3D skeleton",
        "source_video": str(video),
        "normalized_video": str(normalized),
        "video_sha256": _sha256(normalized),
        "static_camera": not args.moving_camera,
        "fps": args.fps,
        "hmr4d_result": str(expected),
        "smplx_global_params": str(smplx_output),
        "world_skeleton": str(skeleton_output),
        "incamera_render": str(render_dir / "1_incam.mp4"),
        "global_render": str(render_dir / "2_global.mp4"),
    }
    (output / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
