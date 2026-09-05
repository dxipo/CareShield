"""流水线位置：io 层——轨迹与事件的 npz 持久化。

schema_version="1.0" 的压缩 npz 是 gaitkit 的磁盘交换格式：GVHMR 关节回归、
事件解码等昂贵步骤的产物落盘后，分析/验证/训练阶段可重复读取而无需重跑模型。
移植自 smpl_pipeline/gait_validation.py:263-316，并补充 schema_version 校验。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from ..core.types import GaitEvents, Trajectory

logger = logging.getLogger(__name__)

TRAJECTORY_SCHEMA_VERSION = "1.0"


def _npz_scalar(value: np.ndarray | str | float | int) -> str:
    array = np.asarray(value)
    return str(array.item()) if array.ndim == 0 else str(array)


def save_trajectory(path: str | Path, trajectory: Trajectory) -> None:
    """把 Trajectory 写入压缩 npz（schema_version="1.0"）。

    布局：time_s [T] float64；joint_names [J] 字符串（按名字典序）；
    joints [T,J,3] float32；source/world_grounded/up_axis/participant/view 标量。
    关节按名字典序堆叠保证读写往返稳定（移植自 gait_validation.py:263-278）。
    """
    path = Path(path)
    names = np.asarray(sorted(trajectory.joints), dtype="U")
    values = np.stack([trajectory.joints[name] for name in names], axis=1).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        schema_version=np.asarray(TRAJECTORY_SCHEMA_VERSION),
        time_s=trajectory.time_s.astype(np.float64),
        joint_names=names,
        joints=values,
        source=np.asarray(trajectory.source),
        world_grounded=np.asarray(trajectory.world_grounded),
        up_axis=np.asarray(trajectory.up_axis, dtype=np.int64),
        participant=np.asarray(trajectory.participant),
        view=np.asarray(trajectory.view),
    )
    logger.debug("trajectory saved: %s", path)


def load_trajectory(path: str | Path) -> Trajectory:
    """读取 npz 轨迹；携带未知 schema_version 时拒绝解析（防静默误读）。"""
    with np.load(path, allow_pickle=False) as data:
        if "schema_version" in data.files:
            version = _npz_scalar(data["schema_version"])
            if version != TRAJECTORY_SCHEMA_VERSION:
                raise ValueError(
                    f"{path}: 轨迹 schema_version={version!r}，本版本 gaitkit 仅支持 "
                    f"{TRAJECTORY_SCHEMA_VERSION!r}；请用生成该文件的 gaitkit 版本读取"
                )
        names = [str(item) for item in data["joint_names"]]
        values = np.asarray(data["joints"], dtype=float)
        return Trajectory(
            time_s=np.asarray(data["time_s"], dtype=float),
            joints={name: values[:, index, :] for index, name in enumerate(names)},
            source=_npz_scalar(data["source"]),
            world_grounded=bool(np.asarray(data["world_grounded"]).item()),
            up_axis=int(np.asarray(data["up_axis"]).item()),
            participant=_npz_scalar(data["participant"]),
            view=_npz_scalar(data["view"]),
        )


def save_events(path: str | Path, events: GaitEvents) -> None:
    """把 GaitEvents 写入压缩 npz（移植自 gait_validation.py:296-305）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        left_down=np.asarray(events.left_down, dtype=float),
        right_down=np.asarray(events.right_down, dtype=float),
        left_up=np.asarray(events.left_up, dtype=float),
        right_up=np.asarray(events.right_up, dtype=float),
        detector=np.asarray(events.detector),
        metadata_json=np.asarray(json.dumps(events.metadata, ensure_ascii=False, allow_nan=False)),
    )
    logger.debug("events saved: %s", path)


def load_events(path: str | Path) -> GaitEvents:
    """读取事件 npz（移植自 gait_validation.py:308-316）。"""
    with np.load(path, allow_pickle=False) as data:
        metadata = {}
        if "metadata_json" in data.files:
            metadata = json.loads(_npz_scalar(data["metadata_json"]))
        return GaitEvents(
            left_down=np.asarray(data["left_down"], dtype=float),
            right_down=np.asarray(data["right_down"], dtype=float),
            left_up=np.asarray(data["left_up"], dtype=float),
            right_up=np.asarray(data["right_up"], dtype=float),
            detector=_npz_scalar(data["detector"]),
            metadata=metadata,
        )
