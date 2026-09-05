"""流水线位置：指标层——关节角不对称分组。

髋/膝角不对称及其均值。逐帧角度在 registry.build_context 中预计算
（移植自 smpl_pipeline/gait_validation.py:752-772），本模块负责标量化。
Xsens 只有 9 个下肢节段：膝角可比，髋屈曲角需要肩/躯干通道故不可比。
"""

from __future__ import annotations

import numpy as np


def _hip_angle_asymmetry_deg(ctx) -> float:
    # gait_validation.py:787 —— mean(|左髋屈曲 − 右髋屈曲|)，逐帧。
    return float(ctx.hip_angle_asymmetry_deg)


def _knee_angle_asymmetry_deg(ctx) -> float:
    # gait_validation.py:788 —— mean(|左膝角 − 右膝角|)，逐帧。
    return float(ctx.knee_angle_asymmetry_deg)


def _hip_knee_asymmetry_deg(ctx) -> float:
    # gait_validation.py:789-791 —— 髋、膝不对称的均值，缺一即 NaN。
    hip, knee = ctx.hip_angle_asymmetry_deg, ctx.knee_angle_asymmetry_deg
    if np.isfinite(hip) and np.isfinite(knee):
        return float((hip + knee) / 2.0)
    return float("nan")


def get_metric_defs() -> tuple:
    """返回本分组 3 项参数定义（MetricDef 延迟导入以避免循环依赖）。"""
    from .registry import MetricDef

    return (
        MetricDef(
            name="hip_angle_asymmetry_deg", cn_name="髋角不对称", unit="degree", group="symmetry",
            tier="extended", toaga_xsens_comparable=False, requires_grounding=True,
            formula="mean(|(180 − ∠(躯干, 左大腿)) − (180 − ∠(躯干, 右大腿))|)，逐帧；需肩部通道",
            func=_hip_angle_asymmetry_deg,
        ),
        MetricDef(
            name="knee_angle_asymmetry_deg", cn_name="膝角不对称", unit="degree", group="symmetry",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="mean(|∠(髋−膝, 踝−膝)_左 − ∠(髋−膝, 踝−膝)_右|)，逐帧",
            func=_knee_angle_asymmetry_deg,
        ),
        MetricDef(
            name="hip_knee_asymmetry_deg", cn_name="髋膝不对称均值", unit="degree", group="symmetry",
            tier="extended", toaga_xsens_comparable=False, requires_grounding=True,
            formula="(髋角不对称 + 膝角不对称) / 2；Xsens 缺髋屈曲参考故不可比对",
            func=_hip_knee_asymmetry_deg,
        ),
    )
