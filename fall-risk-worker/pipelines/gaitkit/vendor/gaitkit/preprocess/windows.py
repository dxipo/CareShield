"""流水线位置：预处理层——时间窗切分。

移植自 smpl_pipeline/gait_deep_learning_input.py:114-124 的 ``_window_starts``：
定长滑窗、尾窗锚定最后一帧、不做零填充。不填充是刻意的——零填充帧不是
真实观测，会污染时序编码器；``frame_mask`` 因此恒为全 True（保留该字段是
为了与未来支持变长窗的模型契约兼容）。
"""

from __future__ import annotations

import numpy as np


def window_starts(n_frames: int, window_frames: int, stride_frames: int) -> list[int]:
    """计算定长滑窗的起始帧列表（尾窗锚定最后一帧，不零填充）。

    原理：stride 均匀开窗后，若末尾不足一个步长，则补一个以最后一帧为右端点
    的尾窗，保证整段序列被完整覆盖；帧数不足一个窗长时抛 ValueError，
    提示改用更长的匀速步行片段（移植自 gait_deep_learning_input.py:114-124）。
    """
    if n_frames < window_frames:
        raise ValueError(
            f"Skeleton segment has {n_frames} frames, fewer than required window {window_frames}; "
            "choose a longer steady-walking segment or an explicitly versioned shorter-window model"
        )
    starts = list(range(0, n_frames - window_frames + 1, stride_frames))
    last = n_frames - window_frames
    if starts[-1] != last:
        starts.append(last)
    return starts


def slice_windows(sequence: np.ndarray, starts: list[int], window_frames: int) -> np.ndarray:
    """按起始帧列表把 [T,...] 序列切成 [N,window_frames,...] 的 float32 堆叠。

    与 window_starts 配套使用；不做任何填充或掩码置位。
    """
    return np.stack([sequence[start : start + window_frames] for start in starts]).astype(np.float32)
