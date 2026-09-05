"""流水线位置：预处理层——时间域处理。

两个函数移植自 smpl_pipeline/gait_validation.py:319-339，数值逻辑完全一致：

- ``resample_trajectory``：把任意采样率的轨迹线性插值到统一时间网格；
- ``butter_lowpass_zero_phase``：4 阶 Butterworth + filtfilt 的零相位低通，
  仅用于 Xsens 参考支路（6 Hz）。视频支路不做此滤波，以免改变
  GaitTransformer 的输入分布（详见 README"预处理链"一节）。
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt

from ..core.types import Trajectory


def resample_trajectory(trajectory: Trajectory, fps: float) -> Trajectory:
    """把轨迹线性插值重采样到 fps Hz 的均匀网格。

    原理：事件检测（30 Hz）与 Xsens 参考（100 Hz）要求统一时间基；np.interp
    逐轴线性插值与参考实现一致（移植自 smpl_pipeline/gait_validation.py:319-329）。
    新网格为 arange(start, end + 0.5/fps, 1/fps)，端点包含规则保持不变。

    输入: 任意 Trajectory；输出: 同关节集合、同坐标约定的等采样 Trajectory。
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    start, end = trajectory.time_s[[0, -1]]
    new_time = np.arange(start, end + 0.5 / fps, 1.0 / fps)
    joints = {
        name: np.column_stack([np.interp(new_time, trajectory.time_s, values[:, axis]) for axis in range(3)])
        for name, values in trajectory.joints.items()
    }
    return Trajectory(
        new_time, joints, trajectory.source, trajectory.world_grounded, trajectory.up_axis,
        trajectory.participant, trajectory.view,
    )


def butter_lowpass_zero_phase(trajectory: Trajectory, cutoff_hz: float = 6.0, order: int = 4) -> Trajectory:
    """对所有关节轨迹做零相位 Butterworth 低通（butter + filtfilt）。

    原理：IMU 派生的节段位置含高频抖动；6 Hz 截止保留步态主频能量
    （步频 ~1.7 Hz，谐波 < 5 Hz）。filtfilt 双向滤波无相位延迟，事件时刻不漂移。
    移植自 smpl_pipeline/gait_validation.py:332-339，跳过条件保持一致：
    采样率不可用、帧数 < max(order*6, 20)、或截止频率 >= Nyquist 时原样返回。
    """
    fps = trajectory.fps
    if not np.isfinite(fps) or len(trajectory.time_s) < max(order * 6, 20) or cutoff_hz >= fps / 2:
        return trajectory
    b, a = butter(order, cutoff_hz / (fps / 2), btype="low")
    joints = {name: filtfilt(b, a, values, axis=0) for name, values in trajectory.joints.items()}
    return Trajectory(
        trajectory.time_s, joints, trajectory.source, trajectory.world_grounded,
        trajectory.up_axis, trajectory.participant, trajectory.view,
    )
