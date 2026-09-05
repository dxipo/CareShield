"""CareShield boundary adapter for GaitKit result files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from careshield_contracts import GaitParameterValue

from app.adapters.command_pipeline import PipelineExecutionError
from app.services.parameter_catalog import map_gaitkit_parameters


@dataclass(frozen=True, slots=True)
class GaitKitResult:
    parameters: list[GaitParameterValue]
    heel_strike_count: int
    toe_off_count: int
    complete_step_count: int
    unavailable_parameter_count: int
    algorithm_id: str
    algorithm_version: str
    metric_definition_version: str
    analysis_fps: float


def load_gaitkit_result(path: Path) -> GaitKitResult:
    if not path.is_file():
        raise PipelineExecutionError("GaitKit completed without a result file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        algorithm = payload["algorithm"]
        metrics = payload["metrics"]
        manifest = payload["metric_manifest"]
        quality = payload["quality"]
        source = payload["source"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PipelineExecutionError("GaitKit result is invalid") from exc
    if payload.get("schema_version") != "2.0" or not isinstance(metrics, dict):
        raise PipelineExecutionError("GaitKit result schema is unsupported")
    parameters = map_gaitkit_parameters(metrics, manifest)
    return GaitKitResult(
        parameters=parameters,
        heel_strike_count=int(quality.get("heel_strike_count", 0)),
        toe_off_count=int(quality.get("toe_off_count", 0)),
        complete_step_count=int(quality.get("complete_step_count", 0)),
        unavailable_parameter_count=sum(not item.available for item in parameters),
        algorithm_id=str(algorithm["id"]),
        algorithm_version=str(algorithm["version"]),
        metric_definition_version=str(algorithm["metric_definition_version"]),
        analysis_fps=float(source["fps"]),
    )
