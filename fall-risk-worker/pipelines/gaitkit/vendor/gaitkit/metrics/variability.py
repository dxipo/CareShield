"""流水线位置：指标层——变异性与对称性分组。

标准差（ddof=1）、变异系数（100×SD/mean）与步时对称指数
（100×|L−R|/((L+R)/2)），统计口径与 smpl_pipeline/gait_validation.py:700-704,
784-785 完全一致（经 core.geometry 的 safe_std/cv_percent/symmetry_index_percent）。
"""

from __future__ import annotations

from ..core.geometry import cv_percent, safe_std, symmetry_index_percent


def _step_time_sd_s(ctx) -> float:
    # gait_validation.py:700。
    return safe_std(ctx.alternating_steps)


def _stride_time_sd_s(ctx) -> float:
    # gait_validation.py:701。
    return safe_std(ctx.stride_times)


def _step_time_cv_percent(ctx) -> float:
    # gait_validation.py:702。
    return cv_percent(ctx.alternating_steps)


def _stride_time_cv_percent(ctx) -> float:
    # gait_validation.py:703。
    return cv_percent(ctx.stride_times)


def _step_length_cv_percent(ctx) -> float:
    # gait_validation.py:784。
    return cv_percent(ctx.step_lengths)


def _step_width_cv_percent(ctx) -> float:
    # gait_validation.py:785。
    return cv_percent(ctx.step_widths)


def _step_time_symmetry_index_percent(ctx) -> float:
    # gait_validation.py:704。
    return symmetry_index_percent(ctx.left_step_times, ctx.right_step_times)


def get_metric_defs() -> tuple:
    """返回本分组 7 项参数定义（MetricDef 延迟导入以避免循环依赖）。"""
    from .registry import MetricDef

    return (
        MetricDef(
            name="step_time_sd_s", cn_name="步时标准差", unit="s", group="variability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=False,
            formula="std(交替步时, ddof=1)",
            func=_step_time_sd_s,
        ),
        MetricDef(
            name="stride_time_sd_s", cn_name="跨步时间标准差", unit="s", group="variability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=False,
            formula="std(同侧跨步时间合并序列, ddof=1)",
            func=_stride_time_sd_s,
        ),
        MetricDef(
            name="step_time_cv_percent", cn_name="步时变异系数", unit="%", group="variability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=False,
            formula="100 × std(交替步时) / mean(交替步时)",
            func=_step_time_cv_percent,
        ),
        MetricDef(
            name="stride_time_cv_percent", cn_name="跨步时间变异系数", unit="%", group="variability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=False,
            formula="100 × std(跨步时间) / mean(跨步时间)",
            func=_stride_time_cv_percent,
        ),
        MetricDef(
            name="step_length_cv_percent", cn_name="步长变异系数", unit="%", group="variability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="100 × std(步长) / mean(步长)",
            func=_step_length_cv_percent,
        ),
        MetricDef(
            name="step_width_cv_percent", cn_name="步宽变异系数", unit="%", group="variability",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=True,
            formula="100 × std(步宽) / mean(步宽)",
            func=_step_width_cv_percent,
        ),
        MetricDef(
            name="step_time_symmetry_index_percent", cn_name="步时对称指数", unit="%", group="symmetry",
            tier="extended", toaga_xsens_comparable=True, requires_grounding=False,
            formula="100 × |mean(左步时) − mean(右步时)| / ((mean(左)+mean(右))/2)",
            func=_step_time_symmetry_index_percent,
        ),
    )
