"""流水线位置：指标层——动态稳定性分组（eCOM / XCoM / eMOS）。

基于倒立摆模型的估计量（移植自 smpl_pipeline/gait_validation.py:556-652）：

- eCOM：双髋中点近似质心，取其在横向轴上的分量；
- XCoM = eCOM + v/ω，ω = sqrt(9.81 / 腿长)，腿长 = ‖hip−knee‖+‖knee−ankle‖
  的逐帧中位数（左右合并）；
- eMOS：支撑转移区间内，支撑踝横向边界到 XCoM 的内侧距离（负值视为越界，
  仅统计 >= 0 的"稳定裕度"样本），给出 min/mean 及髋宽归一化版本。

速度估计使用约 0.25 s 的 Savitzky-Golay 平滑微分——这一步刻意发生在事件
解码之后，只稳定倒立摆模型所需的速度，不改变 GaitTransformer 的输入分布
（原注释精神保留）。
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import savgol_filter

from ..core.geometry import mean_or_nan, next_after
from ..core.types import Trajectory


def smoothed_position_and_velocity(position: np.ndarray, time_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """对一维位置序列做 Savitzky-Golay 平滑并返回 (平滑位置, 速度)。

    移植自 smpl_pipeline/gait_validation.py:556-573：窗口取约 0.25 s 的奇数
    帧长、polyorder=2、mode="interp"；序列过短（<5 帧）时退化为 np.gradient。
    仅用于 XCoM/eMOS 特征，不用于事件解码。
    """
    if len(position) < 5:
        return position, np.gradient(position, time_s) if len(position) > 1 else np.zeros_like(position)
    fps = 1.0 / np.median(np.diff(time_s))
    window = max(5, int(round(0.25 * fps)))
    window += 1 - window % 2  # 约 0.25 s 的奇数窗
    window = min(window, len(position) if len(position) % 2 else len(position) - 1)
    if window < 5:
        smoothed = position
    else:
        smoothed = savgol_filter(position, window_length=window, polyorder=2, mode="interp")
    return smoothed, np.gradient(smoothed, time_s)


def estimated_stability_metrics(
    trajectory: Trajectory,
    left_hs: np.ndarray,
    right_hs: np.ndarray,
    lateral: np.ndarray,
) -> dict[str, float]:
    """计算髋中点 eCOM/XCoM 横向摆动 RMS 与支撑踝横向 eMOS（米制 + 髋宽归一化）。

    移植自 smpl_pipeline/gait_validation.py:576-652（TOAGA MATLAB 工作流的
    同构实现：eCOM=双髋中点、对支撑踝评估稳定裕度）。任一必需关节缺失或
    帧数 < 5 或腿长无效时，6 项全部返回 NaN。
    """
    keys = ("left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle")
    result = {
        "estimated_com_ml_sway_rms_m": float("nan"),
        "extrapolated_com_ml_sway_rms_m": float("nan"),
        "estimated_margin_of_stability_min_m": float("nan"),
        "estimated_margin_of_stability_mean_m": float("nan"),
        "estimated_margin_of_stability_min_hip_width_normalized": float("nan"),
        "estimated_margin_of_stability_mean_hip_width_normalized": float("nan"),
    }
    if any(name not in trajectory.joints for name in keys) or len(trajectory.time_s) < 5:
        return result
    left_hip, right_hip = trajectory.joints["left_hip"], trajectory.joints["right_hip"]
    left_knee, right_knee = trajectory.joints["left_knee"], trajectory.joints["right_knee"]
    left_ankle, right_ankle = trajectory.joints["left_ankle"], trajectory.joints["right_ankle"]
    ecom_ml = ((left_hip + right_hip) / 2.0) @ lateral
    ecom_ml, ecom_velocity_ml = smoothed_position_and_velocity(ecom_ml, trajectory.time_s)
    leg_lengths = np.r_[
        np.linalg.norm(left_hip - left_knee, axis=1) + np.linalg.norm(left_knee - left_ankle, axis=1),
        np.linalg.norm(right_hip - right_knee, axis=1) + np.linalg.norm(right_knee - right_ankle, axis=1),
    ]
    leg_length = float(np.nanmedian(leg_lengths))
    hip_width = float(np.nanmedian(np.abs((left_hip - right_hip) @ lateral)))
    if not np.isfinite(leg_length) or leg_length <= 1e-6:
        return result
    xcom_ml = ecom_ml + ecom_velocity_ml / math.sqrt(9.81 / leg_length)
    result["estimated_com_ml_sway_rms_m"] = float(np.sqrt(np.mean((ecom_ml - np.mean(ecom_ml)) ** 2)))
    result["extrapolated_com_ml_sway_rms_m"] = float(np.sqrt(np.mean((xcom_ml - np.mean(xcom_ml)) ** 2)))

    left_ml, right_ml = left_ankle @ lateral, right_ankle @ lateral
    left_outward = float(np.sign(np.nanmedian(left_ml - right_ml)))
    if left_outward == 0.0:
        left_outward = 1.0

    minima: list[float] = []
    means: list[float] = []
    for support_hs, next_hs, support_ml, outward in (
        (left_hs, right_hs, left_ml, left_outward),
        (right_hs, left_hs, right_ml, -left_outward),
    ):
        for start in support_hs:
            end = next_after(next_hs, float(start))
            if end is None or end <= start:
                continue
            mask = (trajectory.time_s >= start) & (trajectory.time_s <= end)
            if mask.sum() < 3:
                continue
            # 正值表示 XCoM 仍在支撑踝内侧（位于估计的横向支撑面内）。
            inside_margin = (support_ml[mask] - xcom_ml[mask]) * outward
            stable_margin = inside_margin[inside_margin >= 0.0]
            if len(stable_margin):
                minima.append(float(np.min(stable_margin)))
                means.append(float(np.mean(stable_margin)))
    result["estimated_margin_of_stability_min_m"] = mean_or_nan(minima)
    result["estimated_margin_of_stability_mean_m"] = mean_or_nan(means)
    if np.isfinite(hip_width) and hip_width > 1e-6:
        result["estimated_margin_of_stability_min_hip_width_normalized"] = (
            result["estimated_margin_of_stability_min_m"] / hip_width
        )
        result["estimated_margin_of_stability_mean_hip_width_normalized"] = (
            result["estimated_margin_of_stability_mean_m"] / hip_width
        )
    return result


def _make_stability_func(key: str):
    def _func(ctx) -> float:
        # gait_validation.py:793 —— 稳定性子表在 build_context 中统一计算。
        if ctx.stability is None:
            return float("nan")
        return float(ctx.stability[key])

    return _func


def get_metric_defs() -> tuple:
    """返回本分组 6 项参数定义（MetricDef 延迟导入以避免循环依赖）。"""
    from .registry import MetricDef

    return (
        MetricDef(
            name="estimated_com_ml_sway_rms_m", cn_name="估计质心横向摆动 RMS", unit="m", group="stability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="rms(eCOM_ml − mean(eCOM_ml))；eCOM = (左髋 + 右髋)/2 在横向轴上的投影",
            func=_make_stability_func("estimated_com_ml_sway_rms_m"),
        ),
        MetricDef(
            name="extrapolated_com_ml_sway_rms_m", cn_name="外推质心横向摆动 RMS", unit="m", group="stability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="rms(XCoM_ml − mean(XCoM_ml))；XCoM = eCOM + v_ml / sqrt(9.81/腿长)",
            func=_make_stability_func("extrapolated_com_ml_sway_rms_m"),
        ),
        MetricDef(
            name="estimated_margin_of_stability_min_m", cn_name="最小估计稳定裕度", unit="m", group="stability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="mean over 支撑转移区间 of min((支撑踝_ml − XCoM_ml) × 外法向, 仅取 ≥0)",
            func=_make_stability_func("estimated_margin_of_stability_min_m"),
        ),
        MetricDef(
            name="estimated_margin_of_stability_mean_m", cn_name="平均估计稳定裕度", unit="m", group="stability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="mean over 支撑转移区间 of mean((支撑踝_ml − XCoM_ml) × 外法向, 仅取 ≥0)",
            func=_make_stability_func("estimated_margin_of_stability_mean_m"),
        ),
        MetricDef(
            name="estimated_margin_of_stability_min_hip_width_normalized",
            cn_name="最小估计稳定裕度（髋宽归一化）", unit="hip-width", group="stability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="eMOS_min / 髋宽；髋宽 = median(|(左髋 − 右髋) · 横向轴|)",
            func=_make_stability_func("estimated_margin_of_stability_min_hip_width_normalized"),
        ),
        MetricDef(
            name="estimated_margin_of_stability_mean_hip_width_normalized",
            cn_name="平均估计稳定裕度（髋宽归一化）", unit="hip-width", group="stability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="eMOS_mean / 髋宽",
            func=_make_stability_func("estimated_margin_of_stability_mean_hip_width_normalized"),
        ),
    )
