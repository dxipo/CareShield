"""流水线位置：核心层——几何与统计原语。

这里集中放置被事件检测、28 项指标、骨架归一化共用的低层函数：

- ``forward_lateral_axes``：从世界系骨盆水平轨迹用 SVD/PCA 估计行进轴与横轴；
- ``angle_between_deg``：逐帧无向夹角（髋/膝角与躯干前倾角的基础）；
- ``interpolate_at``：在任意事件时刻对关节轨迹做线性插值；
- ``mean_or_nan`` / ``safe_std`` / ``cv_percent`` / ``symmetry_index_percent``：
  带缺失感知的基础统计量（ddof 等数值口径与 smpl_pipeline 完全一致）。

所有函数均为纯函数，不持有状态。
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .types import Trajectory


def forward_lateral_axes(trajectory: Trajectory) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """从世界系骨盆轨迹估计 (forward, lateral, up) 三个单位向量。

    原理（移植自 smpl_pipeline/gait_validation.py:420-438）：步态参数依赖
    "沿行进方向 / 横向"的分解，但相机坐标系朝向任意。骨盆水平位移的主成分
    （SVD 第一右奇异向量）给出行进轴方向，首末位移点积定号，lateral = up × forward
    保证右手系。该方法假设片段以直线匀速步行为主（比赛与 TOAGA 协议均满足）。

    输入: 需要 ``joints["pelvis"]`` 与 ``up_axis``；轨迹不必等采样。
    输出: 三个 shape=(3,) 的单位向量；骨盆无水平运动时抛 ValueError。
    """
    up = np.zeros(3, dtype=float)
    up[trajectory.up_axis] = 1.0
    pelvis = trajectory.joints["pelvis"]
    horizontal = pelvis - pelvis.mean(axis=0, keepdims=True)
    horizontal[:, trajectory.up_axis] = 0.0
    if np.linalg.norm(horizontal) < 1e-8:
        raise ValueError(f"{trajectory.participant}-{trajectory.view}: no horizontal pelvis motion")
    _, _, vectors = np.linalg.svd(horizontal, full_matrices=False)
    forward = vectors[0]
    forward[trajectory.up_axis] = 0.0
    forward /= np.linalg.norm(forward)
    net = pelvis[-1] - pelvis[0]
    if np.dot(forward, net) < 0:
        forward *= -1
    lateral = np.cross(up, forward)
    lateral /= np.linalg.norm(lateral)
    return forward, lateral, up


def angle_between_deg(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """逐帧无向夹角（度），两个向量轨迹形状均为 [T,3]。

    移植自 smpl_pipeline/gait_validation.py:545-553：任一向量范数 <= 1e-9
    的帧输出 NaN（退化帧不伪造角度），其余帧输出 acos(clipped cosine)。
    """
    first_norm = np.linalg.norm(first, axis=-1)
    second_norm = np.linalg.norm(second, axis=-1)
    denominator = first_norm * second_norm
    cosine = np.full(len(first), np.nan, dtype=float)
    valid = denominator > 1e-9
    cosine[valid] = np.sum(first[valid] * second[valid], axis=-1) / denominator[valid]
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def interpolate_at(points: np.ndarray, time_s: np.ndarray, at_s: Sequence[float]) -> np.ndarray:
    """在任意时刻对 [T,3] 关节轨迹做逐轴线性插值（np.interp）。

    移植自 smpl_pipeline/gait_validation.py:521-525。事件时刻（HS/TO）一般不
    落在采样帧上，步长/步宽等参数需要在事件时刻取值；范围外时刻按端点值保持
    （np.interp 的默认行为），与参考实现一致。
    """
    at_s = np.asarray(at_s, dtype=float)
    if not len(at_s):
        return np.empty((0, 3), dtype=float)
    return np.column_stack([np.interp(at_s, time_s, points[:, axis]) for axis in range(3)])


def mean_or_nan(values: Sequence[float]) -> float:
    """有限值的算术平均；无有限值返回 NaN（移植自 gait_validation.py:516-518）。"""
    finite = [value for value in values if np.isfinite(value)]
    return float(np.mean(finite)) if finite else float("nan")


def safe_std(values: Sequence[float]) -> float:
    """有限值的样本标准差（ddof=1）；少于 2 个有限值返回 NaN。

    移植自 smpl_pipeline/gait_validation.py:528-530（_std_or_nan）。
    """
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    return float(np.std(finite, ddof=1)) if len(finite) >= 2 else float("nan")


def cv_percent(values: Sequence[float]) -> float:
    """变异系数 100 × std/mean；|mean| <= 1e-9 或统计量缺失时返回 NaN。

    移植自 smpl_pipeline/gait_validation.py:533-535（_cv_percent）。
    """
    mean, std = mean_or_nan(values), safe_std(values)
    return float(std / mean * 100.0) if np.isfinite(mean) and np.isfinite(std) and abs(mean) > 1e-9 else float("nan")


def symmetry_index_percent(left_values: Sequence[float], right_values: Sequence[float]) -> float:
    """步时对称指数 100 × |L−R| / ((L+R)/2)；0 表示完全对称。

    移植自 smpl_pipeline/gait_validation.py:538-542（_symmetry_index_percent）。
    """
    left, right = mean_or_nan(left_values), mean_or_nan(right_values)
    denominator = (left + right) / 2.0
    return float(abs(left - right) / denominator * 100.0) if np.isfinite(denominator) and denominator > 1e-9 else float("nan")


def next_after(values: np.ndarray, time_s: float) -> float | None:
    """有序数组中严格大于 time_s 的第一个值；没有则 None。

    移植自 smpl_pipeline/gait_validation.py:506-508（searchsorted side="right"）。
    """
    position = int(np.searchsorted(values, time_s, side="right"))
    return float(values[position]) if position < len(values) else None


def previous_before(values: np.ndarray, time_s: float) -> float | None:
    """有序数组中严格小于 time_s 的最后一个值；没有则 None。

    移植自 smpl_pipeline/gait_validation.py:511-513（searchsorted side="left"）。
    """
    position = int(np.searchsorted(values, time_s, side="left")) - 1
    return float(values[position]) if position >= 0 else None
