"""流水线位置：指标层——时空参数分组（8 核心 + 步宽/摆臂/抬脚/躯干前倾）。

每项 MetricDef 的 func 只从 MetricContext 取预计算中间量并做最后一步标量化，
数值逻辑与 smpl_pipeline/gait_validation.py:692-793 完全一致（来源行号见各注释）。
本模块的函数在 registry 装配时通过 get_metric_defs() 注册。
"""

from __future__ import annotations

import numpy as np

from ..core.geometry import mean_or_nan


def _cadence_spm(ctx) -> float:
    # gait_validation.py:693 —— 60 / 平均交替步时。
    return float(60.0 / np.mean(ctx.alternating_steps)) if ctx.alternating_steps else float("nan")


def _step_time_s(ctx) -> float:
    # gait_validation.py:694。
    return mean_or_nan(ctx.alternating_steps)


def _stride_time_s(ctx) -> float:
    # gait_validation.py:695 —— 同侧相邻 HS 间隔（左右合并）。
    return mean_or_nan(ctx.stride_times)


def _stance_time_s(ctx) -> float:
    # gait_validation.py:696 —— 同侧 HS 到其后 TO。
    return mean_or_nan(ctx.stance)


def _swing_time_s(ctx) -> float:
    # gait_validation.py:697 —— 同侧 TO 到下一次 HS。
    return mean_or_nan(ctx.swing)


def _double_support_time_s(ctx) -> float:
    # gait_validation.py:699 —— HS 后 0.5 s 内对侧 TO 分量均值 ×2（= 每周期双支撑总量）。
    return 2.0 * mean_or_nan(ctx.double_support_components)


def _step_length_m(ctx) -> float:
    # gait_validation.py:777 —— 交替 HS 间骨盆沿行进轴位移绝对值的均值。
    return mean_or_nan(ctx.step_lengths)


def _gait_speed_m_s(ctx) -> float:
    # gait_validation.py:779-781 —— 平均步长 / 平均步时。
    mean_step_length = mean_or_nan(ctx.step_lengths)
    mean_step_time = mean_or_nan(ctx.alternating_steps)
    if np.isfinite(mean_step_length) and np.isfinite(mean_step_time) and mean_step_time > 0:
        return float(mean_step_length / mean_step_time)
    return float("nan")


def _step_width_m(ctx) -> float:
    # gait_validation.py:778 —— HS 时双踝横向间距的均值。
    return mean_or_nan(ctx.step_widths)


def _arm_swing_amplitude_m(ctx) -> float:
    # gait_validation.py:782 —— 腕相对骨盆行进轴峰峰值的左右均值。
    return mean_or_nan(ctx.arm_swing_amplitudes)


def _foot_lift_height_m(ctx) -> float:
    # gait_validation.py:783 —— 周期内踝竖直 max − min(两端点) 的均值。
    return mean_or_nan(ctx.foot_lifts)


def _trunk_stoop_angle_deg(ctx) -> float:
    # gait_validation.py:786（计算见 registry.build_context 的躯干段）。
    return float(ctx.trunk_stoop_angle_deg)


def get_metric_defs() -> tuple:
    """返回本分组 12 项参数定义（MetricDef 延迟导入以避免循环依赖）。"""
    from .registry import MetricDef

    return (
        MetricDef(
            name="cadence_spm", cn_name="步频", unit="steps/min", group="rhythm",
            tier="core", toaga_xsens_comparable=True, requires_grounding=False,
            formula="60 / 平均交替步时（相邻左右足跟着地间隔的均值）",
            func=_cadence_spm,
        ),
        MetricDef(
            name="step_time_s", cn_name="步时", unit="s", group="timing",
            tier="core", toaga_xsens_comparable=True, requires_grounding=False,
            formula="mean(交替 HS 间隔)",
            func=_step_time_s,
        ),
        MetricDef(
            name="stride_time_s", cn_name="跨步时间", unit="s", group="timing",
            tier="core", toaga_xsens_comparable=True, requires_grounding=False,
            formula="mean(同侧相邻 HS 间隔，左右合并)",
            func=_stride_time_s,
        ),
        MetricDef(
            name="stance_time_s", cn_name="支撑时间", unit="s", group="phase",
            tier="core", toaga_xsens_comparable=False, requires_grounding=False,
            formula="mean(同侧 HS -> 其后 TO)；Xsens 无 TO 通道故不可比对",
            func=_stance_time_s,
        ),
        MetricDef(
            name="swing_time_s", cn_name="摆动时间", unit="s", group="phase",
            tier="core", toaga_xsens_comparable=False, requires_grounding=False,
            formula="mean(同侧 TO -> 下一次 HS)；Xsens 无 TO 通道故不可比对",
            func=_swing_time_s,
        ),
        MetricDef(
            name="double_support_time_s", cn_name="双支撑时间", unit="s", group="phase",
            tier="core", toaga_xsens_comparable=False, requires_grounding=False,
            formula="2 × mean(HS 后 0.5 s 内对侧 TO 的分量)（= 每周期双支撑总量）",
            func=_double_support_time_s,
        ),
        MetricDef(
            name="step_length_m", cn_name="步长", unit="m", group="spatial",
            tier="core", toaga_xsens_comparable=True, requires_grounding=True,
            formula="mean(|骨盆(HS_{i+1}) − 骨盆(HS_i) 在行进轴上的投影|)，交替 HS 序列",
            func=_step_length_m,
        ),
        MetricDef(
            name="gait_speed_m_s", cn_name="步速", unit="m/s", group="spatiotemporal",
            tier="core", toaga_xsens_comparable=True, requires_grounding=True,
            formula="平均步长 / 平均步时",
            func=_gait_speed_m_s,
        ),
        MetricDef(
            name="step_width_m", cn_name="步宽", unit="m", group="spatial",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="mean(|(踝_支撑 − 踝_对侧) 在横向轴上的投影|)，逐次 HS",
            func=_step_width_m,
        ),
        MetricDef(
            name="arm_swing_amplitude_m", cn_name="摆臂幅度", unit="m", group="upper_body",
            tier="extended", toaga_xsens_comparable=False, requires_grounding=True,
            formula="mean( ptp(腕 − 骨盆 在行进轴上的投影) )，左右取均值；Xsens 无腕部通道",
            func=_arm_swing_amplitude_m,
        ),
        MetricDef(
            name="foot_lift_height_m", cn_name="抬脚高度", unit="m", group="clearance",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="mean( 周期内踝竖直 max − min(周期两端点) )，逐同侧 HS 周期",
            func=_foot_lift_height_m,
        ),
        MetricDef(
            name="trunk_stoop_angle_deg", cn_name="躯干前倾角", unit="degree", group="posture",
            tier="extended", toaga_xsens_comparable=False, requires_grounding=True,
            formula="mean( arccos(|单位化(肩中点 − 骨盆) · up|) )，逐帧；Xsens 无肩部通道",
            func=_trunk_stoop_angle_deg,
        ),
    )
