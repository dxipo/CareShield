"""流水线位置：核心层——关节布局常量与名称映射。

不同上游模型输出不同的关节集合与顺序：GVHMR 走 SMPL-X 回归、MotionBERT
输出 H36M-17、TOAGA Xsens 只有 9 个节段位置、GastNet/VideoPose3D 使用另一套
H36M 命名。本模块把这些布局固化为常量并提供映射表，使 io 层与下游
（VisionMD 事件检测要求严格的 H36M-17 顺序、骨架张量层同样如此）可以显式
校验与转换，而不是靠"约定俗称"的索引。

命名规范：gaitkit 内部统一使用 H36M-17 语义名（pelvis/right_hip/...）。
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

import numpy as np

# H36M-17 布局：MotionBERT 与 GaitTransformer 适配层共用的规范顺序
# （移植自 smpl_pipeline/gait_validation.py:62-68 的 H36M_JOINTS）。
H36M_17: tuple[str, ...] = (
    "pelvis", "right_hip", "right_knee", "right_ankle", "left_hip",
    "left_knee", "left_ankle", "spine", "neck", "nose", "head",
    "left_shoulder", "left_elbow", "left_wrist", "right_shoulder",
    "right_elbow", "right_wrist",
)

# SMPL 前 22 个体关节的标准顺序（SMPL-X 前 22 关节与 SMPL 一致）。
SMPL_22: tuple[str, ...] = (
    "pelvis", "left_hip", "right_hip", "spine1", "left_knee", "right_knee",
    "spine2", "left_ankle", "right_ankle", "spine3", "left_foot", "right_foot",
    "neck", "left_collar", "right_collar", "head", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
)

# TOAGA Xsens CSV 提供的 9 个节段位置（io/xsens.py 的列映射按此顺序命名）。
XSENS_9: tuple[str, ...] = (
    "pelvis", "right_hip", "right_knee", "right_ankle", "right_toe",
    "left_hip", "left_knee", "left_ankle", "left_toe",
)

# GastNet/VideoPose3D 常用的 H36M 17 关节命名。语义与 H36M_17 相同但名称不同，
# 通过 GASTNET_TO_H36M 重命名后可直接复用 gaitkit 的全部下游逻辑。
GASTNET_17: tuple[str, ...] = (
    "hip", "right_hip", "right_knee", "right_foot", "left_hip",
    "left_knee", "left_foot", "spine", "thorax", "neck", "head",
    "left_shoulder", "left_elbow", "left_hand", "right_shoulder",
    "right_elbow", "right_hand",
)

# GastNet 命名 -> gaitkit 规范命名（仅列出需要改名的关节，其余同名直通）。
GASTNET_TO_H36M: dict[str, str] = {
    "hip": "pelvis",
    "right_foot": "right_ankle",
    "left_foot": "left_ankle",
    "thorax": "neck",
    "neck": "nose",
    "left_hand": "left_wrist",
    "right_hand": "right_wrist",
}

# SMPL-X 扩展关节回归器中，前 22 个体关节之后按 SMPL 顺序排列；该索引把
# SMPL-X 关节重排为 H36M-17（移植自 smpl_pipeline/gait_validation.py:71-73）。
SMPLX_TO_H36M: tuple[int, ...] = (0, 2, 5, 8, 1, 4, 7, 3, 12, 15, 15, 16, 18, 20, 17, 19, 21)

# SMPL-X 扩展回归器中具有临床意义的足端 landmark（足尖/足跟）。
# 与 H36M-17 并存：GaitTransformer 只吃 17 关节，空间参数可用更丰富的解剖点
# （移植自 smpl_pipeline/gait_validation.py:78-83）。
SMPLX_AUXILIARY_JOINTS: dict[str, int] = {
    "left_toe": 57,
    "left_heel": 59,
    "right_toe": 60,
    "right_heel": 62,
}


def require_joints(available: Iterable[str] | Mapping[str, object], required: Sequence[str], owner: str = "trajectory") -> None:
    """校验必需关节齐全，缺失时抛出列出缺失名的 ValueError。

    原理：VisionMD 解码与骨架张量都依赖严格的 H36M-17 集合；在边界处显式
    报错（fail fast）比 downstream 出现 KeyError 更容易定位数据通路问题。
    """
    names = set(available)
    missing = [name for name in required if name not in names]
    if missing:
        raise ValueError(f"{owner}: 缺少必需关节: {missing}")


def rename_joints(joints: Mapping[str, np.ndarray], mapping: Mapping[str, str]) -> dict[str, np.ndarray]:
    """按映射表重命名关节字典（同名直通），返回新字典，不改原对象。

    输入: joints {旧名: [T,3]}，mapping {旧名: 新名}。
    输出: {新名: [T,3]}；若两个旧名映射到同一新名，后出现者覆盖，调用方应
    保证映射是一对一的（例如 GASTNET_TO_H36M）。
    """
    return {mapping.get(name, name): values for name, values in joints.items()}
