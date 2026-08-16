from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from careshield_contracts import AlgorithmResult, AlgorithmTask


def valid_result(**overrides) -> dict:
    payload = {
        "result_id": uuid4(),
        "task": AlgorithmTask.PIPELINE_TEST,
        "model_id": "pipeline-tester",
        "model_version": "1.0",
        "device_id": None,
        "source_timestamp": None,
        "result_timestamp": datetime.now(timezone.utc),
        "label": "pipeline_ok",
        "score": None,
        "level": None,
        "latency_ms": None,
        "metadata": {"message": "test"},
        "simulated": True,
    }
    payload.update(overrides)
    return payload


def test_algorithm_result_accepts_explicit_simulated_pipeline_test() -> None:
    result = AlgorithmResult.model_validate(valid_result())
    assert result.task == AlgorithmTask.PIPELINE_TEST
    assert result.simulated is True


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_algorithm_result_rejects_score_outside_unit_interval(score: float) -> None:
    with pytest.raises(ValidationError):
        AlgorithmResult.model_validate(valid_result(score=score))


def test_algorithm_result_rejects_unknown_task() -> None:
    with pytest.raises(ValidationError):
        AlgorithmResult.model_validate(valid_result(task="unknown"))


def test_algorithm_result_requires_simulated_flag() -> None:
    payload = valid_result()
    payload.pop("simulated")
    with pytest.raises(ValidationError):
        AlgorithmResult.model_validate(payload)


def test_pipeline_test_cannot_claim_to_be_real() -> None:
    with pytest.raises(ValidationError):
        AlgorithmResult.model_validate(valid_result(simulated=False))
