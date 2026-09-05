"""Portable TOML configuration for the end-to-end workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG = """# Paths are resolved relative to this file.
[tools]
gvhmr_root = "third_party/GVHMR"
gait_transformer_root = "third_party/GaitTransformer"
gvhmr_python = ".venv-gvhmr/bin/python"
visionmd_python = ".venv-visionmd/bin/python"
# Leave empty to use Gaitkit's headless adapter.  A custom GVHMR entry script
# may be specified relative to gvhmr_root.
gvhmr_entry = ""

[runtime]
output_dir = "outputs"
target_fps = 30.0
static_camera = true
fail_fast = false

[segmentation]
backend = "motion"
yolo_model = ""
minimum_segment_seconds = 3.0
maximum_gap_seconds = 1.0
analysis_fps = 15.0
minimum_motion = 0.0015
minimum_presence_ratio = 0.25
analysis_width = 640

[events]
window_frames = 60
use_xla = false
"""


@dataclass(frozen=True)
class ToolSettings:
    gvhmr_root: Path
    gait_transformer_root: Path
    gvhmr_python: str
    visionmd_python: str
    gvhmr_entry: Path | None


@dataclass(frozen=True)
class RuntimeSettings:
    output_dir: Path
    target_fps: float = 30.0
    static_camera: bool = True
    fail_fast: bool = False


@dataclass(frozen=True)
class SegmentationSettings:
    backend: str = "motion"
    yolo_model: Path | None = None
    minimum_segment_seconds: float = 3.0
    maximum_gap_seconds: float = 1.0
    analysis_fps: float = 15.0
    minimum_motion: float = 0.0015
    minimum_presence_ratio: float = 0.25
    analysis_width: int = 640


@dataclass(frozen=True)
class EventSettings:
    window_frames: int = 60
    use_xla: bool = False


@dataclass(frozen=True)
class Settings:
    path: Path
    tools: ToolSettings
    runtime: RuntimeSettings
    segmentation: SegmentationSettings
    events: EventSettings


def _table(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    return value


def _path(base: Path, value: object, *, optional: bool = False) -> Path | None:
    text = str(value or "").strip()
    if not text and optional:
        return None
    if not text:
        raise ValueError("a required path is empty")
    candidate = Path(text).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def _command(base: Path, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Python interpreter command is empty")
    # Bare commands such as 'python' are resolved through PATH.  Anything that
    # looks like a path is made relative to the configuration file.
    if "/" not in text and "\\" not in text:
        return text
    candidate = Path(text).expanduser()
    return str(candidate if candidate.is_absolute() else (base / candidate).resolve())


def load_settings(path: str | Path = "gaitkit.toml") -> Settings:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"configuration file not found: {path.name}; run 'gaitkit init' first")
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    base = path.parent
    tools = _table(payload, "tools")
    runtime = _table(payload, "runtime")
    segmentation = _table(payload, "segmentation")
    events = _table(payload, "events")
    backend = str(segmentation.get("backend", "motion")).lower()
    if backend not in {"motion", "yolo"}:
        raise ValueError("segmentation.backend must be 'motion' or 'yolo'")
    settings = Settings(
        path=path,
        tools=ToolSettings(
            gvhmr_root=_path(base, tools.get("gvhmr_root")),  # type: ignore[arg-type]
            gait_transformer_root=_path(base, tools.get("gait_transformer_root")),  # type: ignore[arg-type]
            gvhmr_python=_command(base, tools.get("gvhmr_python", "python")),
            visionmd_python=_command(base, tools.get("visionmd_python", "python")),
            gvhmr_entry=_path(base, tools.get("gvhmr_entry", ""), optional=True),
        ),
        runtime=RuntimeSettings(
            output_dir=_path(base, runtime.get("output_dir", "outputs")),  # type: ignore[arg-type]
            target_fps=float(runtime.get("target_fps", 30.0)),
            static_camera=bool(runtime.get("static_camera", True)),
            fail_fast=bool(runtime.get("fail_fast", False)),
        ),
        segmentation=SegmentationSettings(
            backend=backend,
            yolo_model=_path(base, segmentation.get("yolo_model", ""), optional=True),
            minimum_segment_seconds=float(segmentation.get("minimum_segment_seconds", 3.0)),
            maximum_gap_seconds=float(segmentation.get("maximum_gap_seconds", 1.0)),
            analysis_fps=float(segmentation.get("analysis_fps", 15.0)),
            minimum_motion=float(segmentation.get("minimum_motion", 0.0015)),
            minimum_presence_ratio=float(segmentation.get("minimum_presence_ratio", 0.25)),
            analysis_width=int(segmentation.get("analysis_width", 640)),
        ),
        events=EventSettings(
            window_frames=int(events.get("window_frames", 60)),
            use_xla=bool(events.get("use_xla", False)),
        ),
    )
    if abs(settings.runtime.target_fps - 30.0) > 0.1:
        raise ValueError("the GVHMR-to-GaitTransformer route is fixed at 30 Hz")
    return settings


def write_default_config(path: str | Path = "gaitkit.toml", *, overwrite: bool = False) -> Path:
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"configuration file already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return path
