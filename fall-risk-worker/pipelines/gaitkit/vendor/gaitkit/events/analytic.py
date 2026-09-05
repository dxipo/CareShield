"""流水线位置：事件检测层——解析式（骨盆相对前后极值）检测器。

移植自 smpl_pipeline/gait_validation.py:441-496 的 analytic_events 及其辅助函数，
数值逻辑完全一致：

- 信号：足（优先足尖，缺失用踝）相对骨盆在行进轴上的投影；
- HS：detrend 后信号的 MAD  prominence 峰值（前向极值）；
- TO：该 HS 与下一同侧 HS 之间的局部极小（后向极值）；
- 周期过滤：相邻同侧 HS 间隔须落在 [0.55, 2.5] s。

它是 Xsens 参考轨迹的事件来源，也是无 GaitTransformer 环境下的后备；
刻意不作为视频骨架上 GaitTransformer 的替代品（原注释精神保留）。
要求 world_grounded=True（行进轴依赖世界系骨盆轨迹）。
"""

from __future__ import annotations

import logging

import numpy as np
from scipy.signal import detrend, find_peaks

from ..core.geometry import forward_lateral_axes
from ..core.types import GaitEvents, Trajectory

logger = logging.getLogger(__name__)


def _unique_spaced_peaks(signal: np.ndarray, fps: float) -> np.ndarray:
    """从前向足-骨盆位移信号提取足跟着地候选帧。

    移植自 smpl_pipeline/gait_validation.py:441-447：最小峰距 0.35 s，
    prominence = max(0.005, 1.4826×MAD×0.25)（对异常帧鲁棒）。
    """
    distance = max(1, int(round(0.35 * fps)))
    robust_scale = np.median(np.abs(signal - np.median(signal))) * 1.4826
    prominence = max(0.005, robust_scale * 0.25)
    peaks, _ = find_peaks(signal, distance=distance, prominence=prominence)
    return peaks.astype(int)


def _toe_offs_after(heel_strikes: np.ndarray, signal: np.ndarray) -> np.ndarray:
    """每个 HS 与下一同侧 HS 之间的局部极小作为足尖离地（移植 gait_validation.py:450-459）。"""
    result: list[int] = []
    for index, heel in enumerate(heel_strikes):
        next_heel = heel_strikes[index + 1] if index + 1 < len(heel_strikes) else len(signal) - 1
        if next_heel - heel < 3:
            continue
        local_min = heel + int(np.argmin(signal[heel : next_heel + 1]))
        if local_min > heel:
            result.append(local_min)
    return np.asarray(result, dtype=int)


class AnalyticEventDetector:
    """解析式事件检测器（无外部依赖，available() 恒为 True）。

    适用：Xsens 等米制世界系轨迹；要求 world_grounded=True（行进轴来自
    骨盆水平轨迹的 PCA）。对根相对轨迹抛 ValueError，绝不伪造事件。
    """

    name = "pelvis_relative_fore_aft_extrema"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, trajectory: Trajectory, height_mm: float = 1700.0) -> GaitEvents:
        """在世界系轨迹上检测 HS/TO（height_mm 仅满足协议，本方法不使用）。

        步骤（移植自 smpl_pipeline/gait_validation.py:462-496）：
        1) PCA 行进轴；2) 足相对骨盆前向投影；3) detrend + MAD prominence 找 HS；
        4) 周期 [0.55, 2.5] s 过滤边缘毛刺；5) HS 间局部极小定 TO。
        """
        if not trajectory.world_grounded:
            raise ValueError("Analytic spatial event detection requires world-grounded trajectories")
        forward, _, _ = forward_lateral_axes(trajectory)
        pelvis = trajectory.joints["pelvis"]
        left = trajectory.joints.get("left_toe", trajectory.joints["left_ankle"])
        right = trajectory.joints.get("right_toe", trajectory.joints["right_ankle"])
        left_signal = (left - pelvis) @ forward
        right_signal = (right - pelvis) @ forward
        left_hs = _unique_spaced_peaks(detrend(left_signal), trajectory.fps)
        right_hs = _unique_spaced_peaks(detrend(right_signal), trajectory.fps)

        # 要求合理的步周期，剔除文件边缘的短信号毛刺。
        def plausible(values: np.ndarray) -> np.ndarray:
            if len(values) < 2:
                return values
            periods = np.diff(trajectory.time_s[values])
            keep = np.r_[True, (periods >= 0.55) & (periods <= 2.5)]
            return values[keep]

        left_hs, right_hs = plausible(left_hs), plausible(right_hs)
        logger.debug("analytic events: left_hs=%d right_hs=%d", len(left_hs), len(right_hs))
        return GaitEvents(
            left_down=trajectory.time_s[left_hs],
            right_down=trajectory.time_s[right_hs],
            left_up=trajectory.time_s[_toe_offs_after(left_hs, left_signal)],
            right_up=trajectory.time_s[_toe_offs_after(right_hs, right_signal)],
            detector=self.name,
        )
