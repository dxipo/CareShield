"""核心层：数据契约、关节布局与几何/统计原语。"""

from .geometry import (
    angle_between_deg,
    cv_percent,
    forward_lateral_axes,
    interpolate_at,
    mean_or_nan,
    next_after,
    previous_before,
    safe_std,
    symmetry_index_percent,
)
from .joints import (
    GASTNET_17,
    GASTNET_TO_H36M,
    H36M_17,
    SMPL_22,
    SMPLX_AUXILIARY_JOINTS,
    SMPLX_TO_H36M,
    XSENS_9,
    rename_joints,
    require_joints,
)
from .types import AnalysisResult, GaitEvents, Trajectory

__all__ = [
    "AnalysisResult",
    "GaitEvents",
    "Trajectory",
    "H36M_17",
    "SMPL_22",
    "XSENS_9",
    "GASTNET_17",
    "GASTNET_TO_H36M",
    "SMPLX_TO_H36M",
    "SMPLX_AUXILIARY_JOINTS",
    "rename_joints",
    "require_joints",
    "forward_lateral_axes",
    "angle_between_deg",
    "interpolate_at",
    "mean_or_nan",
    "safe_std",
    "cv_percent",
    "symmetry_index_percent",
    "next_after",
    "previous_before",
]
