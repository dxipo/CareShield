"""Controller for RGB screening, GVHMR, event decoding and 28 parameters."""

from __future__ import annotations

import csv
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .settings import Settings
from .video import MotionWalkingSegmenter, YoloPersonDetector, write_cfr_segment


VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".avi", ".mkv", ".m4v"})


def _content_id(path: Path) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    digest.update(str(size).encode("ascii"))
    with path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
        if size > 1024 * 1024:
            handle.seek(max(0, size - 1024 * 1024))
            digest.update(handle.read(1024 * 1024))
    return digest.hexdigest()[:12]


def discover_videos(source: str | Path) -> list[Path]:
    source = Path(source).expanduser().resolve()
    if source.is_file():
        if source.suffix.lower() not in VIDEO_SUFFIXES:
            raise ValueError("the input file is not a supported video")
        return [source]
    if not source.is_dir():
        raise FileNotFoundError("input video or directory is unavailable")
    return sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES)


@dataclass(frozen=True)
class SegmentRun:
    video_id: str
    segment_index: int
    status: str
    output: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "segment_index": self.segment_index,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


class GaitkitWorkflow:
    """End-to-end workflow with separate GVHMR and GaitTransformer environments."""

    def __init__(self, settings: Settings, *, output_dir: str | Path | None = None) -> None:
        self.settings = settings
        self.output_dir = Path(output_dir).resolve() if output_dir else settings.runtime.output_dir
        self.package_root = Path(__file__).resolve().parents[1]

    def _environment(self, extra_python_path: Path | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        entries = [str(self.package_root)]
        if extra_python_path is not None:
            entries.insert(0, str(extra_python_path))
        if environment.get("PYTHONPATH"):
            entries.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(entries)
        return environment

    def _worker(self, command: list[str], *, extra_python_path: Path | None = None) -> None:
        subprocess.run(command, env=self._environment(extra_python_path), check=True)

    def _segmenter(self) -> tuple[MotionWalkingSegmenter, Callable | None]:
        cfg = self.settings.segmentation
        segmenter = MotionWalkingSegmenter(
            min_segment_sec=cfg.minimum_segment_seconds,
            max_gap_sec=cfg.maximum_gap_seconds,
            analysis_fps=cfg.analysis_fps,
            min_motion=cfg.minimum_motion,
            min_presence_ratio=cfg.minimum_presence_ratio,
            analysis_width=cfg.analysis_width,
        )
        detector = None
        if cfg.backend == "yolo":
            if cfg.yolo_model is None:
                raise ValueError("segmentation.yolo_model is required when backend='yolo'")
            detector = YoloPersonDetector(cfg.yolo_model)
        return segmenter, detector

    def _run_segment(self, video: Path, video_id: str, segment, height_mm: float) -> SegmentRun:
        segment_dir = self.output_dir / f"video_{video_id}" / f"segment_{segment.index:03d}"
        segment_dir.mkdir(parents=True, exist_ok=True)
        relative_output = str(segment_dir.relative_to(self.output_dir)).replace("\\", "/")
        try:
            normalized = write_cfr_segment(
                video,
                segment_dir / "input_30hz.mp4",
                segment,
                target_fps=self.settings.runtime.target_fps,
            )
            minimum_frames = int(round(self.settings.segmentation.minimum_segment_seconds * 30.0))
            if normalized.frame_count < minimum_frames or abs(normalized.fps - 30.0) > 0.1:
                raise ValueError("normalized walking segment is too short or is not 30 Hz")

            gvhmr_command = [
                self.settings.tools.gvhmr_python,
                "-m", "gaitkit.workers.gvhmr_stage",
                "--video", str(segment_dir / "input_30hz.mp4"),
                "--output", str(segment_dir),
                "--gvhmr-root", str(self.settings.tools.gvhmr_root),
                "--expected-frames", str(normalized.frame_count),
            ]
            if self.settings.runtime.static_camera:
                gvhmr_command.append("--static-camera")
            if self.settings.tools.gvhmr_entry is not None:
                gvhmr_command.extend(("--gvhmr-entry", str(self.settings.tools.gvhmr_entry)))
            self._worker(gvhmr_command, extra_python_path=self.settings.tools.gvhmr_root)

            analysis_command = [
                self.settings.tools.visionmd_python,
                "-m", "gaitkit.workers.analyze_stage",
                "--trajectory", str(segment_dir / "world_skeleton_21.npz"),
                "--height-mm", str(float(height_mm)),
                "--output", str(segment_dir),
                "--gait-transformer-root", str(self.settings.tools.gait_transformer_root),
                "--window-frames", str(self.settings.events.window_frames),
            ]
            if self.settings.events.use_xla:
                analysis_command.append("--use-xla")
            self._worker(analysis_command, extra_python_path=self.settings.tools.gait_transformer_root)
            return SegmentRun(video_id, segment.index, "ok", relative_output)
        except Exception as error:
            if self.settings.runtime.fail_fast:
                raise
            return SegmentRun(video_id, segment.index, "failed", relative_output, str(error).splitlines()[0][:500])

    def _write_combined_parameters(self, runs: list[SegmentRun]) -> None:
        rows: list[dict[str, Any]] = []
        metric_names: list[str] = []
        for run in runs:
            if run.status != "ok":
                continue
            path = self.output_dir / run.output / "gait_metrics_28.csv"
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                items = list(csv.DictReader(handle))
            if not metric_names:
                metric_names = [item["name"] for item in items]
            row: dict[str, Any] = {"video_id": run.video_id, "segment_index": run.segment_index}
            row.update({item["name"]: item["value"] for item in items})
            rows.append(row)
        if not rows:
            return
        with (self.output_dir / "gait_metrics_28_all.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["video_id", "segment_index", *metric_names])
            writer.writeheader()
            writer.writerows(rows)

    def run(self, source: str | Path, *, height_mm: float | Callable[[Path], float]) -> dict[str, Any]:
        videos = discover_videos(source)
        if not videos:
            raise ValueError("no supported video files were found")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        runs: list[SegmentRun] = []
        videos_without_candidates = 0
        for video in videos:
            video_id = _content_id(video)
            segmenter, detector = self._segmenter()
            _, segments = segmenter.analyze(video, detector=detector)
            if not segments:
                videos_without_candidates += 1
                continue
            resolved_height = float(height_mm(video) if callable(height_mm) else height_mm)
            for segment in segments:
                runs.append(self._run_segment(video, video_id, segment, resolved_height))
        self._write_combined_parameters(runs)
        return {
            "video_count": len(videos),
            "videos_without_walking_segments": videos_without_candidates,
            "segment_count": len(runs),
            "successful_segments": sum(run.status == "ok" for run in runs),
            "failed_segments": sum(run.status == "failed" for run in runs),
            "segments": [run.to_dict() for run in runs],
        }


def height_lookup_from_csv(path: str | Path) -> Callable[[Path], float]:
    rows: dict[str, float] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[str(row["video"])] = float(row["height_mm"])

    def resolve(video: Path) -> float:
        if video.name not in rows:
            raise KeyError(f"height table has no row for input video: {video.name}")
        return rows[video.name]

    return resolve


def check_environment(settings: Settings) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "ok" if ok else "missing", "detail": detail})

    add("GVHMR repository", settings.tools.gvhmr_root.is_dir(), "repository directory")
    add("GVHMR package", (settings.tools.gvhmr_root / "hmr4d").is_dir(), "hmr4d Python package")
    add(
        "GaitTransformer repository",
        (settings.tools.gait_transformer_root / "gait_transformer").is_dir(),
        "gait_transformer Python package",
    )
    add(
        "GaitTransformer weights",
        (settings.tools.gait_transformer_root / "gait_transformer" / "assets" / "model_v0.2.h5").is_file(),
        "model_v0.2.h5",
    )
    if settings.tools.gvhmr_entry is not None:
        add("GVHMR entry", settings.tools.gvhmr_entry.is_file(), "configured entry script")
    else:
        add("GVHMR entry", True, "bundled headless adapter")

    probes = (
        ("GVHMR environment", settings.tools.gvhmr_python, settings.tools.gvhmr_root, "import torch, cv2, hmr4d, gaitkit; assert torch.cuda.is_available()"),
        ("GaitTransformer environment", settings.tools.visionmd_python, settings.tools.gait_transformer_root, "import numpy, scipy, tensorflow, gait_transformer, gaitkit"),
    )
    package_root = Path(__file__).resolve().parents[1]
    for name, interpreter, extra, expression in probes:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(extra), str(package_root), environment.get("PYTHONPATH", "")))
        try:
            result = subprocess.run(
                [interpreter, "-c", expression], env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60,
            )
            add(name, result.returncode == 0, "required imports and runtime")
        except (OSError, subprocess.TimeoutExpired):
            add(name, False, "Python interpreter or required imports")
    return {"status": "ok" if all(item["status"] == "ok" for item in checks) else "incomplete", "checks": checks}
