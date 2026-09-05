import json

import pytest

from app.adapters.command_pipeline import PipelineExecutionError
from app.adapters.gaitkit import load_gaitkit_result
from app.services.parameter_catalog import GAITKIT_PARAMETER_NAMES


def payload() -> dict:
    return {
        "schema_version": "2.0",
        "algorithm": {
            "id": "gaitkit-world-gait-parameters",
            "version": "2.0-careshield.1",
            "metric_definition_version": "gaitkit-metrics-2.0",
        },
        "metrics": {name: 1.0 for name in GAITKIT_PARAMETER_NAMES},
        "metric_manifest": [
            {"name": name, "display_name": name, "unit": "m", "group": "test"}
            for name in GAITKIT_PARAMETER_NAMES
        ],
        "quality": {
            "heel_strike_count": 8,
            "toe_off_count": 8,
            "complete_step_count": 7,
        },
        "source": {"fps": 30.0},
    }


def test_loads_versioned_gaitkit_result(tmp_path) -> None:
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(payload()), encoding="utf-8")

    result = load_gaitkit_result(result_file)

    assert result.algorithm_id == "gaitkit-world-gait-parameters"
    assert result.algorithm_version == "2.0-careshield.1"
    assert result.complete_step_count == 7
    assert result.unavailable_parameter_count == 0
    assert len(result.parameters) == 28


def test_rejects_unknown_or_incomplete_metric_contract(tmp_path) -> None:
    invalid = payload()
    invalid["metrics"].pop("cadence_spm")
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical 28"):
        load_gaitkit_result(result_file)


def test_missing_result_uses_safe_pipeline_error(tmp_path) -> None:
    with pytest.raises(PipelineExecutionError, match="without a result"):
        load_gaitkit_result(tmp_path / "missing.json")
