import numpy as np
import pytest

from app.input_adapter import TARGET_JOINTS, adapt_world_skeleton


SOURCE_NAMES = [
    "pelvis", "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel", "left_toe",
    "right_toe", "spine", "neck", "head", "head_top", "left_shoulder",
    "left_elbow", "left_wrist", "right_shoulder", "right_elbow", "right_wrist",
]


def skeleton(frames: int = 60) -> np.ndarray:
    value = np.zeros((frames, len(SOURCE_NAMES), 3), dtype=np.float32)
    time = np.linspace(0, 1, frames, dtype=np.float32)
    for index in range(len(SOURCE_NAMES)):
        value[:, index, 0] = time + index * 0.01
        value[:, index, 1] = index * 0.03
        value[:, index, 2] = 1 + index * 0.04
    return value


def test_adapter_produces_exact_stgcn_contract() -> None:
    result = adapt_world_skeleton(skeleton(), SOURCE_NAMES)
    assert result.shape == (3, 120, 17, 1)
    assert result.dtype == np.float32
    assert np.isfinite(result).all()
    assert np.allclose(result[:, :, 0, 0], 0.0)
    assert len(TARGET_JOINTS) == 17


def test_adapter_rejects_missing_required_joint() -> None:
    with pytest.raises(ValueError, match="missing required joints"):
        adapt_world_skeleton(skeleton()[:, :-1], SOURCE_NAMES[:-1])


def test_adapter_interpolates_isolated_missing_values() -> None:
    value = skeleton()
    value[20, SOURCE_NAMES.index("left_knee"), 0] = np.nan
    assert np.isfinite(adapt_world_skeleton(value, SOURCE_NAMES)).all()
