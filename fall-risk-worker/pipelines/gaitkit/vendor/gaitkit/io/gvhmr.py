"""流水线位置：io 层——GVHMR（路径 1：RGB 视频 -> SMPL -> 米制世界系 3D 骨架）。

GVHMR 官方产物 ``hmr4d_results.pt`` 存的是 SMPL-X 参数；要得到命名关节轨迹
需要用 smplx 模型做一次前向回归（依赖 torch + GVHMR 仓库的 make_smplx）。
这两个依赖都很重，因此：

- ``load_hmr4d_results`` 采用**懒加载**：只有真正调用时才 import torch，
  缺依赖时给出清晰报错；完整前向必须在已有的 gvhmr 环境中运行
  （移植自 smpl_pipeline/gait_validation.py:833-891）。
- 日常分析与验证建议直接读取已由该前向生成的关节 npz
  （``load_joint_npz``，即 trajectory_io.load_trajectory），gaitkit 主体
  不需要 torch。

GVHMR 输出约定：米制、地面对齐（world_grounded=True）、Y-up（up_axis=1）。
关节集合 = H36M-17 + 足尖/足跟（SMPL-X 扩展 landmark）。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np

from ..core.joints import H36M_17, SMPLX_AUXILIARY_JOINTS, SMPLX_TO_H36M
from ..core.types import Trajectory
from .trajectory_io import load_trajectory

logger = logging.getLogger(__name__)

_TORCH_HINT = (
    "load_hmr4d_results 需要 PyTorch 与 GVHMR 环境（smplx_utils.make_smplx）。\n"
    "请在 gaitkit.toml 中配置 GVHMR 仓库和 Python 环境，或使用\n"
    "gaitkit.io.load_joint_npz 读取已经生成的关节 npz。"
)


def load_joint_npz(path: str | Path) -> Trajectory:
    """读取已版本化的关节 npz（schema_version 校验见 trajectory_io）。"""
    return load_trajectory(path)


def load_hmr4d_results(
    path: str | Path,
    *,
    gvhmr_root: str | Path,
    fps: float = 30.0,
    participant: str = "unknown",
    view: str = "unknown",
    batch_size: int = 128,
) -> Trajectory:
    """从 GVHMR 官方 ``hmr4d_results.pt`` 回归命名三维关节轨迹。

    原理：SMPL-X 参数（姿态/形状/平移）经 make_smplx("supermotion") 前向得到
    扩展关节，再按 SMPLX_TO_H36M 重排出 H36M-17，并保留足尖/足跟 landmark
    （移植自 smpl_pipeline/gait_validation.py:833-891）。

    时钟说明（保留原注释要点）：GVHMR 官方 demo 输出的工作容器标称 30 Hz，
    但历史产物是逐帧复制而非真实重采样；生产输入应先用 ffmpeg 真重采样到
    30 Hz CFR，再送入 GVHMR，此时逐帧时间戳与 30 Hz 时钟一致。本函数不再
    读取视频猜 fps，帧率由调用方显式传入（默认 30 Hz）。

    输入: path 为 hmr4d_results.pt；gvhmr_root 为 GVHMR 仓库根（含 hmr4d 包）。
    输出: Trajectory(world_grounded=True, up_axis=1, source="GVHMR")，单位米。
    """
    path = Path(path)
    gvhmr_root = Path(gvhmr_root)
    try:
        import torch
    except ImportError as error:  # pragma: no cover - 依赖外部环境
        raise RuntimeError(_TORCH_HINT) from error
    if not gvhmr_root.is_dir():
        raise FileNotFoundError(f"缺少 GVHMR 仓库: {gvhmr_root}")

    previous_cwd = Path.cwd()
    try:
        os.chdir(gvhmr_root)
        sys.path.insert(0, str(gvhmr_root))
        from hmr4d.utils.smplx_utils import make_smplx

        prediction = torch.load(path, map_location="cpu")
        params = prediction["smpl_params_global"]
        model = make_smplx("supermotion").eval()
        joint_batches: list[np.ndarray] = []
        with torch.no_grad():
            for start in range(0, len(params["transl"]), batch_size):
                batch = {name: value[start : start + batch_size] for name, value in params.items()}
                joint_batches.append(model(**batch).joints.detach().cpu().numpy())
    finally:
        os.chdir(previous_cwd)
        if str(gvhmr_root) in sys.path:
            sys.path.remove(str(gvhmr_root))

    joints_smpl = np.concatenate(joint_batches, axis=0)
    if joints_smpl.shape[1] <= max(SMPLX_AUXILIARY_JOINTS.values()):
        raise ValueError(
            f"GVHMR SMPL-X 输出只有 {joints_smpl.shape[1]} 个关节；足跟/足尖扩展 landmark 不可用"
        )
    h36m = joints_smpl[:, np.asarray(SMPLX_TO_H36M, dtype=int)]
    time_s = np.arange(len(h36m), dtype=float) / fps
    logger.info("GVHMR joints regressed: %s (%d frames @ %.3f Hz)", path.name, len(h36m), fps)
    return Trajectory(
        time_s=time_s,
        joints={
            **{name: h36m[:, index] for index, name in enumerate(H36M_17)},
            **{name: joints_smpl[:, index] for name, index in SMPLX_AUXILIARY_JOINTS.items()},
        },
        source="GVHMR",
        world_grounded=True,
        up_axis=1,
        participant=participant,
        view=view,
    )
