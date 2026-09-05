"""流水线位置：预处理层——骨架空间归一化（神经网络输入专用）。

这四个步骤移植自 smpl_pipeline/gait_deep_learning_input.py:127-192 中
``build_skeleton_tensor_batch`` 的空间处理部分，数值逻辑完全一致：

1. ``pelvis_center``：逐帧减骨盆，得到根相对坐标（消除世界平移）；
2. ``align_heading``：用 PCA 行进轴把坐标基变换到 [lateral, up, forward]
   （消除相机朝向差异，要求 world_grounded）；
3. ``scale_by_height``：除以实测身高（米），得到无量纲坐标（消除体型差异）；
4. ``add_velocity_channels``：np.gradient 数值微分得到速度通道。

注意：这些变换只作用于喂给神经网络的"归一化副本"；步态参数计算始终使用
原始世界系轨迹（见 metrics/ 与 README 的数据契约）。
"""

from __future__ import annotations

import numpy as np

from ..core.geometry import forward_lateral_axes
from ..core.types import Trajectory


def pelvis_center(points: np.ndarray, pelvis_index: int = 0) -> np.ndarray:
    """逐帧减去骨盆坐标，把 [T,J,3] 变为根相对坐标。

    原理：姿态的肢体构型与人在世界中的平移无关；减根后网络不必学习平移不变性。
    移植自 gait_deep_learning_input.py:151-152（points - points[:, :1, :]）。
    """
    return points - points[:, pelvis_index : pelvis_index + 1, :]


def heading_basis(trajectory: Trajectory) -> np.ndarray:
    """由世界系轨迹估计归一化基矩阵，列为 [lateral, up, forward]。

    返回 shape=(3,3) 的基 B；对齐坐标 = 原坐标 @ B（行向量右乘）。
    移植自 gait_deep_learning_input.py:158-159 的 basis = stack((lateral, up, forward))。
    """
    forward, lateral, up = forward_lateral_axes(trajectory)
    return np.stack((lateral, up, forward), axis=1)


def align_heading(points: np.ndarray, basis: np.ndarray) -> np.ndarray:
    """把 [T,J,3] 世界坐标右乘基矩阵，变换到 [lateral, up, forward] 分量。

    原理：不同相机/片段的行进方向在世界系中任意；变换后"前进"恒为 +z 分量，
    网络输入与采集视角解耦。移植自 gait_deep_learning_input.py:160（points @ basis）。
    """
    return points @ basis


def scale_by_height(points: np.ndarray, height_mm: float) -> np.ndarray:
    """把米制坐标除以实测身高（米），得到无量纲坐标。

    原理：老年受试者身高差异大，按身高归一后同一动作模式的数值范围可比。
    移植自 gait_deep_learning_input.py:163-166（height_m = height_mm/1000）。
    """
    height_m = height_mm / 1000.0
    return points / height_m


def add_velocity_channels(points: np.ndarray, fps: float) -> np.ndarray:
    """对 [T,J,3] 位置序列做 np.gradient 数值微分，返回同形速度序列。

    原理：速度是步态动态的关键线索；在完整序列上微分（而非逐窗）可避免
    窗口边界的差分截断误差（移植自 gait_deep_learning_input.py:170，
    np.gradient(points, 1.0 / target_fps, axis=0)）。
    """
    return np.gradient(points, 1.0 / fps, axis=0)
