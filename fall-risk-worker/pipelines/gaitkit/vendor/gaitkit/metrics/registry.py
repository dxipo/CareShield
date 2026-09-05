"""流水线位置：指标层——28 项步态参数的注册表与统一计算入口。

设计要点（可解释性第一）：

- 每项参数是一个 ``MetricDef``：中英文名称、单位、分组、证据层级
  （core=VisionMD 已验证 8 项 / extended=跌倒风险探索 20 项）、
  TOAGA Xsens 可比性、人类可读公式、计算函数，全部集中可审计；
- ``build_context`` 把 ``gait_metrics`` 的共享中间量（交替 HS 序列、支撑/摆动/
  双支撑分量、行进轴、步长序列、稳定度量……）一次性算好，各 MetricDef.func
  只做"从中间量到标量"的最后一步，数值逻辑与
  smpl_pipeline/gait_validation.py:655-794 完全一致（逐段标注来源行号）；
- **world_grounded 硬门控**：非世界系轨迹上，空间/稳定性参数一律 NaN，
  绝不输出伪米值（对应原实现 gait_validation.py:712-713 的提前返回）。

各参数的具体计算函数分散在 spatiotemporal/variability/asymmetry/stability
四个模块，本文件底部按规范顺序装配 ``METRIC_REGISTRY``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from ..core.geometry import (
    angle_between_deg,
    forward_lateral_axes,
    interpolate_at,
    mean_or_nan,
    next_after,
)
from ..core.types import GaitEvents, Trajectory
from .stability import estimated_stability_metrics

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricDef:
    """一项步态参数的完整可解释定义。

    属性:
        name: 机器名（snake_case，写入 JSON/CSV）；
        cn_name: 中文名（审计与展示）；
        unit: 单位（米/秒/%/度/髋宽归一化）；
        group: 语义分组（rhythm/timing/phase/spatial/variability/symmetry/...）；
        tier: 证据层级，"core"=VisionMD 已验证主参数，"extended"=跌倒风险探索参数；
        toaga_xsens_comparable: 是否可与 TOAGA Xsens 参考比对（公开 Xsens 无
             toe-off/接触通道，故 stance/swing/double_support 等不可比）；
        requires_grounding: True 时非世界系轨迹上一律输出 NaN（硬门控）；
        formula: 人类可读公式（写清定义，不依赖代码阅读）；
        func: 从 MetricContext 计算标量的函数。
    """

    name: str
    cn_name: str
    unit: str
    group: str
    tier: str
    toaga_xsens_comparable: bool
    requires_grounding: bool
    formula: str
    func: Callable[["MetricContext"], float]


@dataclass(frozen=True)
class MetricContext:
    """28 项参数共享的预计算中间量（由 build_context 一次性构建）。

    空间字段（axes/step_lengths/...）在非世界系轨迹上为 None 或 NaN；
    门控在 compute_all 中执行，各 MetricDef.func 不需要重复判断。
    """

    trajectory: Trajectory
    events: GaitEvents
    grounded: bool
    alternating_step_intervals: tuple  # ((start, end, side), ...) side ∈ {"left","right"}
    alternating_steps: tuple
    left_step_times: tuple
    right_step_times: tuple
    stride_times: tuple
    stance: tuple
    swing: tuple
    double_support_components: tuple
    forward: Optional[np.ndarray]
    lateral: Optional[np.ndarray]
    up: Optional[np.ndarray]
    step_lengths: tuple
    step_widths: tuple
    arm_swing_amplitudes: tuple
    foot_lifts: tuple
    trunk_stoop_angle_deg: float
    hip_angle_asymmetry_deg: float
    knee_angle_asymmetry_deg: float
    stability: Optional[dict]


def build_context(trajectory: Trajectory, events: GaitEvents) -> MetricContext:
    """由轨迹 + 事件构建共享中间量（gait_metrics 主体的等价移植）。

    移植自 smpl_pipeline/gait_validation.py:662-793，保持事件配对规则、
    阈值（0.5 s 双支撑窗、1e-8 躯干范数）、插值方式与 ddof 口径完全一致。
    """
    # --- 交替足跟着地序列（gait_validation.py:662-673） ---
    left_hs, right_hs = np.sort(events.left_down), np.sort(events.right_down)
    left_to, right_to = np.sort(events.left_up), np.sort(events.right_up)
    all_hs = sorted([(time, "left") for time in left_hs] + [(time, "right") for time in right_hs])
    alternating_step_intervals = [
        (all_hs[index][0], all_hs[index + 1][0], all_hs[index + 1][1])
        for index in range(len(all_hs) - 1)
        if all_hs[index + 1][1] != all_hs[index][1]
    ]
    alternating_steps = [end - start for start, end, _ in alternating_step_intervals]
    left_step_times = [end - start for start, end, side in alternating_step_intervals if side == "left"]
    right_step_times = [end - start for start, end, side in alternating_step_intervals if side == "right"]
    stride_times = np.r_[np.diff(left_hs), np.diff(right_hs)] if len(left_hs) + len(right_hs) else np.asarray([])

    # --- 支撑/摆动/双支撑分量（gait_validation.py:676-690） ---
    stance: list[float] = []
    swing: list[float] = []
    double_support_components: list[float] = []
    for heel_strikes, toe_offs, other_toe_offs in ((left_hs, left_to, right_to), (right_hs, right_to, left_to)):
        for heel in heel_strikes:
            toe = next_after(toe_offs, heel)
            next_heel = next_after(heel_strikes, heel)
            other_toe = next_after(other_toe_offs, heel)
            if toe is not None and toe > heel:
                stance.append(toe - heel)
            if toe is not None and next_heel is not None and next_heel > toe:
                swing.append(next_heel - toe)
            if other_toe is not None and 0.0 < other_toe - heel <= 0.5:
                # 该足跟着地后的初始双支撑分量。
                double_support_components.append(other_toe - heel)

    grounded = bool(trajectory.world_grounded)
    if not grounded:
        # 硬门控（gait_validation.py:712-713）：非世界系轨迹不算任何空间量。
        return MetricContext(
            trajectory=trajectory,
            events=events,
            grounded=False,
            alternating_step_intervals=tuple(alternating_step_intervals),
            alternating_steps=tuple(alternating_steps),
            left_step_times=tuple(left_step_times),
            right_step_times=tuple(right_step_times),
            stride_times=tuple(stride_times.tolist()),
            stance=tuple(stance),
            swing=tuple(swing),
            double_support_components=tuple(double_support_components),
            forward=None,
            lateral=None,
            up=None,
            step_lengths=(),
            step_widths=(),
            arm_swing_amplitudes=(),
            foot_lifts=(),
            trunk_stoop_angle_deg=float("nan"),
            hip_angle_asymmetry_deg=float("nan"),
            knee_angle_asymmetry_deg=float("nan"),
            stability=None,
        )

    # --- 空间量（gait_validation.py:715-772） ---
    forward, lateral, up = forward_lateral_axes(trajectory)
    # 步长：相邻交替 HS 时刻骨盆沿行进轴的位移绝对值（VisionMD 主定义）。
    pelvis = trajectory.joints["pelvis"]
    step_lengths: list[float] = []
    for start, end, _ in alternating_step_intervals:
        pelvis_at_events = interpolate_at(pelvis, trajectory.time_s, [start, end])
        step_lengths.append(abs(float((pelvis_at_events[1] - pelvis_at_events[0]) @ forward)))

    # 步宽：每次 HS 时双踝在横向轴的间距（TOAGA/CARE-PD 踝中心约定）。
    left_foot = trajectory.joints["left_ankle"]
    right_foot = trajectory.joints["right_ankle"]
    step_widths: list[float] = []
    for times, foot, other in ((left_hs, left_foot, right_foot), (right_hs, right_foot, left_foot)):
        foot_at_hs = interpolate_at(foot, trajectory.time_s, times)
        other_at_hs = interpolate_at(other, trajectory.time_s, times)
        step_widths.extend(np.abs((foot_at_hs - other_at_hs) @ lateral).tolist())

    # 摆臂幅度：腕相对骨盆沿行进轴的峰峰值，左右取均值。
    arm_swing_amplitudes: list[float] = []
    for wrist_name in ("left_wrist", "right_wrist"):
        wrist = trajectory.joints.get(wrist_name)
        if wrist is not None:
            arm_swing_amplitudes.append(float(np.ptp((wrist - pelvis) @ forward)))

    # 抬脚高度：每个同侧 HS 周期内踝竖直轨迹 max − min(两端点)。
    foot_lifts: list[float] = []
    for ankle, heel_strikes in ((left_foot, left_hs), (right_foot, right_hs)):
        vertical = ankle[:, trajectory.up_axis]
        for start, end in zip(heel_strikes[:-1], heel_strikes[1:]):
            mask = (trajectory.time_s >= start) & (trajectory.time_s <= end)
            if mask.sum() < 3:
                continue
            segment = vertical[mask]
            endpoints = np.asarray([segment[0], segment[-1]])
            foot_lifts.append(float(np.max(segment) - np.min(endpoints)))

    left_hip, right_hip = trajectory.joints["left_hip"], trajectory.joints["right_hip"]
    left_knee, right_knee = trajectory.joints["left_knee"], trajectory.joints["right_knee"]
    left_knee_angle = angle_between_deg(left_hip - left_knee, left_foot - left_knee)
    right_knee_angle = angle_between_deg(right_hip - right_knee, right_foot - right_knee)
    knee_asymmetry = mean_or_nan(np.abs(left_knee_angle - right_knee_angle).tolist())
    hip_asymmetry = float("nan")
    trunk_stoop_angle = float("nan")
    if "left_shoulder" in trajectory.joints and "right_shoulder" in trajectory.joints:
        shoulder_midpoint = (trajectory.joints["left_shoulder"] + trajectory.joints["right_shoulder"]) / 2.0
        trunk = shoulder_midpoint - pelvis
        # 躯干偏离竖直轴的角度：0° 表示肩-骨盆轴完全竖直。
        trunk_norm = np.linalg.norm(trunk, axis=1)
        valid_trunk = trunk_norm > 1e-8
        if np.any(valid_trunk):
            trunk_unit = trunk[valid_trunk] / trunk_norm[valid_trunk, None]
            cos_to_up = np.clip(np.abs(trunk_unit @ up), -1.0, 1.0)
            trunk_stoop_angle = float(np.mean(np.degrees(np.arccos(cos_to_up))))
        left_hip_flexion = 180.0 - angle_between_deg(trunk, left_knee - left_hip)
        right_hip_flexion = 180.0 - angle_between_deg(trunk, right_knee - right_hip)
        hip_asymmetry = mean_or_nan(np.abs(left_hip_flexion - right_hip_flexion).tolist())

    stability = estimated_stability_metrics(trajectory, left_hs, right_hs, lateral)
    return MetricContext(
        trajectory=trajectory,
        events=events,
        grounded=True,
        alternating_step_intervals=tuple(alternating_step_intervals),
        alternating_steps=tuple(alternating_steps),
        left_step_times=tuple(left_step_times),
        right_step_times=tuple(right_step_times),
        stride_times=tuple(stride_times.tolist()),
        stance=tuple(stance),
        swing=tuple(swing),
        double_support_components=tuple(double_support_components),
        forward=forward,
        lateral=lateral,
        up=up,
        step_lengths=tuple(step_lengths),
        step_widths=tuple(step_widths),
        arm_swing_amplitudes=tuple(arm_swing_amplitudes),
        foot_lifts=tuple(foot_lifts),
        trunk_stoop_angle_deg=trunk_stoop_angle,
        hip_angle_asymmetry_deg=hip_asymmetry,
        knee_angle_asymmetry_deg=knee_asymmetry,
        stability=stability,
    )


# ---------------------------------------------------------------------------
# 注册表装配：四个分组模块提供 MetricDef，本文件按规范顺序排序。
# ---------------------------------------------------------------------------

from . import asymmetry as _asymmetry_defs  # noqa: E402
from . import spatiotemporal as _spatiotemporal_defs  # noqa: E402
from . import stability as _stability_defs  # noqa: E402
from . import variability as _variability_defs  # noqa: E402

# 8 项 VisionMD 已验证主参数（移植 VISIONMD_PRIMARY_METRICS，gait_validation.py:85-94）。
CORE8: tuple[str, ...] = (
    "cadence_spm",
    "step_time_s",
    "stride_time_s",
    "stance_time_s",
    "swing_time_s",
    "double_support_time_s",
    "step_length_m",
    "gait_speed_m_s",
)

# 20 项跌倒风险探索参数（移植 FALL_RISK_EXTENDED_METRICS，gait_validation.py:99-120）。
RISK_EXT20: tuple[str, ...] = (
    "step_width_m",
    "arm_swing_amplitude_m",
    "foot_lift_height_m",
    "step_time_sd_s",
    "stride_time_sd_s",
    "step_time_cv_percent",
    "stride_time_cv_percent",
    "step_length_cv_percent",
    "step_width_cv_percent",
    "step_time_symmetry_index_percent",
    "trunk_stoop_angle_deg",
    "hip_angle_asymmetry_deg",
    "knee_angle_asymmetry_deg",
    "hip_knee_asymmetry_deg",
    "estimated_com_ml_sway_rms_m",
    "extrapolated_com_ml_sway_rms_m",
    "estimated_margin_of_stability_min_m",
    "estimated_margin_of_stability_mean_m",
    "estimated_margin_of_stability_min_hip_width_normalized",
    "estimated_margin_of_stability_mean_hip_width_normalized",
)

CANONICAL_METRICS: tuple[str, ...] = CORE8 + RISK_EXT20

# 可与 TOAGA Xsens 参考比对的 21 项白名单（移植 TOAGA_XSENS_REFERENCE_METRICS，
# gait_validation.py:132-141；公开 Xsens 无 toe-off 通道，故时相参数不可比）。
XSENS_COMPARABLE21: frozenset = frozenset({
    "cadence_spm", "step_time_s", "stride_time_s", "step_length_m", "gait_speed_m_s",
    "step_width_m", "foot_lift_height_m", "step_time_sd_s", "stride_time_sd_s",
    "step_time_cv_percent", "stride_time_cv_percent", "step_length_cv_percent",
    "step_width_cv_percent", "step_time_symmetry_index_percent", "knee_angle_asymmetry_deg",
    "estimated_com_ml_sway_rms_m", "extrapolated_com_ml_sway_rms_m",
    "estimated_margin_of_stability_min_m", "estimated_margin_of_stability_mean_m",
    "estimated_margin_of_stability_min_hip_width_normalized",
    "estimated_margin_of_stability_mean_hip_width_normalized",
})

_ALL_DEFS = (
    _spatiotemporal_defs.get_metric_defs()
    + _variability_defs.get_metric_defs()
    + _asymmetry_defs.get_metric_defs()
    + _stability_defs.get_metric_defs()
)
_DEFS_BY_NAME = {metric.name: metric for metric in _ALL_DEFS}
_missing = [name for name in CANONICAL_METRICS if name not in _DEFS_BY_NAME]
if _missing:  # 装配自检：注册表必须恰好覆盖 28 项规范参数。
    raise RuntimeError(f"指标注册表缺少规范参数: {_missing}")

METRIC_REGISTRY: tuple[MetricDef, ...] = tuple(_DEFS_BY_NAME[name] for name in CANONICAL_METRICS)


def compute_all(trajectory: Trajectory, events: GaitEvents) -> dict[str, float]:
    """计算全部 28 项步态参数，返回按规范顺序的 {name: float}。

    硬门控：trajectory.world_grounded=False 时，requires_grounding 的参数一律
    NaN（绝不伪造）；时间类参数（步频/步时/时相/变异性/对称性）照常计算。
    """
    context = build_context(trajectory, events)
    result: dict[str, float] = {}
    for metric in METRIC_REGISTRY:
        if metric.requires_grounding and not context.grounded:
            result[metric.name] = float("nan")
        else:
            result[metric.name] = float(metric.func(context))
    return result


def metric_manifest() -> list[dict[str, str]]:
    """导出注册表的可读清单（名称/中文名/单位/公式/层级/可比性），供文档与审计。"""
    return [
        {
            "name": metric.name,
            "cn_name": metric.cn_name,
            "unit": metric.unit,
            "group": metric.group,
            "tier": metric.tier,
            "toaga_xsens_comparable": str(metric.toaga_xsens_comparable),
            "requires_grounding": str(metric.requires_grounding),
            "formula": metric.formula,
        }
        for metric in METRIC_REGISTRY
    ]
