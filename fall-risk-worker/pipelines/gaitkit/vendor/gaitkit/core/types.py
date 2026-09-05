"""流水线位置：核心数据契约层。

本模块定义 gaitkit 全链路的三种交换格式：

- ``Trajectory``：命名三维关节轨迹（io 层把 Xsens/GVHMR/MotionBERT 产物翻译成它）；
- ``GaitEvents``：步态事件时刻（HS=heel strike 足跟着地 / TO=toe-off 足尖离地）；
- ``AnalysisResult``：一次行走片段的事件、28 项参数与计算来源。

下游（事件检测、28 项指标、神经网络张量）只消费这些类型，不感知上游来源，
这是"可替换数据通路 + 统一分析内核"设计的基础。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True, eq=False)
class Trajectory:
    """命名三维关节轨迹，附带显式坐标系约定（移植自 smpl_pipeline/gait_validation.py:144-174）。

    坐标系约定（可解释性的根基）：

    - ``time_s``: 单调递增的秒级时间轴，形状 ``[T]``；
    - ``joints``: ``{关节名: [T, 3] float64}``，单位为米；
    - ``up_axis``: 世界系竖直轴下标（GVHMR/SMPL 为 1 即 Y-up，TOAGA Xsens CSV 为 2 即 Z-up）；
    - ``world_grounded``: True 表示轨迹处于米制世界系且地面对齐，空间与稳定性
      参数才有物理意义；False（如 MotionBERT 根相对输出）时这些参数一律输出
      NaN，绝不伪造（硬门控，见 metrics/registry.py）。

    ``eq=False``：numpy 数组字段无法做逐元素相等比较，冻结仅保证字段不可重新绑定。
    """

    time_s: np.ndarray
    joints: dict[str, np.ndarray]
    source: str
    world_grounded: bool
    up_axis: int
    participant: str = "unknown"
    view: str = "unknown"

    @property
    def fps(self) -> float:
        """由中位数帧间隔推定的采样率（Hz），对个别丢帧鲁棒。"""
        if len(self.time_s) < 2:
            return float("nan")
        return float(1.0 / np.median(np.diff(self.time_s)))

    @property
    def duration_s(self) -> float:
        """片段时长（秒）。"""
        if len(self.time_s) < 2:
            return 0.0
        return float(self.time_s[-1] - self.time_s[0])

    def copy_window(self, start_s: float, end_s: float) -> "Trajectory":
        """截取闭区间 [start_s, end_s] 内的帧。

        少于 10 帧视为同步窗口配置错误并抛 ``ValueError``
        （移植自 smpl_pipeline/gait_validation.py:162-174，阈值 10 保持不变）。
        """
        mask = (self.time_s >= start_s) & (self.time_s <= end_s)
        if int(mask.sum()) < 10:
            raise ValueError(
                f"{self.participant}-{self.view}: synchronized window contains fewer than 10 frames"
            )
        return Trajectory(
            time_s=self.time_s[mask],
            joints={name: values[mask] for name, values in self.joints.items()},
            source=self.source,
            world_grounded=self.world_grounded,
            up_axis=self.up_axis,
            participant=self.participant,
            view=self.view,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容字典（数组转嵌套列表）。"""
        return {
            "time_s": np.asarray(self.time_s, dtype=float).tolist(),
            "joints": {name: np.asarray(values, dtype=float).tolist() for name, values in self.joints.items()},
            "source": self.source,
            "world_grounded": bool(self.world_grounded),
            "up_axis": int(self.up_axis),
            "participant": self.participant,
            "view": self.view,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Trajectory":
        """从 ``to_dict`` 产物重建轨迹。"""
        return cls(
            time_s=np.asarray(payload["time_s"], dtype=float),
            joints={str(name): np.asarray(values, dtype=float) for name, values in payload["joints"].items()},
            source=str(payload["source"]),
            world_grounded=bool(payload["world_grounded"]),
            up_axis=int(payload["up_axis"]),
            participant=str(payload.get("participant", "unknown")),
            view=str(payload.get("view", "unknown")),
        )


@dataclass(frozen=True, eq=False)
class GaitEvents:
    """步态事件时刻（秒）。

    ``down`` 为足跟着地（heel strike / contact），``up`` 为足尖离地（toe-off）
    （移植自 smpl_pipeline/gait_validation.py:177-185 的 Events）。
    ``detector`` 记录产生事件的检测器名，写入 AnalysisResult 的 provenance。
    """

    left_down: np.ndarray
    right_down: np.ndarray
    left_up: np.ndarray
    right_up: np.ndarray
    detector: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def n_left_hs(self) -> int:
        return int(len(self.left_down))

    @property
    def n_right_hs(self) -> int:
        return int(len(self.right_down))

    @property
    def total_heel_strikes(self) -> int:
        return self.n_left_hs + self.n_right_hs

    def in_window(self, start_s: float, end_s: float) -> "GaitEvents":
        """截取落在闭区间内的事件（移植自 smpl_pipeline/gait_validation.py:499-503）。"""

        def clip(values: np.ndarray) -> np.ndarray:
            return values[(values >= start_s) & (values <= end_s)]

        return GaitEvents(
            clip(self.left_down),
            clip(self.right_down),
            clip(self.left_up),
            clip(self.right_up),
            self.detector,
            dict(self.metadata),
        )

    def swap_laterality(self, *, reason: str) -> "GaitEvents":
        """返回左右事件互换后的副本，并永久记录修正原因。

        TOAGA CORE8 的同视频时间轴对齐发现：当前 MotionBERT→GaitTransformer
        适配器的左右命名与 GVHMR/SMPL 约定系统性相反。该方法只交换标签，不移动
        事件时刻；原始事件保持不变，避免在检测器内部做不可审计的隐式修正。
        """
        metadata = dict(self.metadata)
        metadata.update(
            laterality_transform="swap_left_right",
            laterality_corrected=True,
            laterality_reason=str(reason),
        )
        return GaitEvents(
            left_down=np.asarray(self.right_down, dtype=float).copy(),
            right_down=np.asarray(self.left_down, dtype=float).copy(),
            left_up=np.asarray(self.right_up, dtype=float).copy(),
            right_up=np.asarray(self.left_up, dtype=float).copy(),
            detector=self.detector,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_down": np.asarray(self.left_down, dtype=float).tolist(),
            "right_down": np.asarray(self.right_down, dtype=float).tolist(),
            "left_up": np.asarray(self.left_up, dtype=float).tolist(),
            "right_up": np.asarray(self.right_up, dtype=float).tolist(),
            "detector": self.detector,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GaitEvents":
        return cls(
            left_down=np.asarray(payload["left_down"], dtype=float),
            right_down=np.asarray(payload["right_down"], dtype=float),
            left_up=np.asarray(payload["left_up"], dtype=float),
            right_up=np.asarray(payload["right_up"], dtype=float),
            detector=str(payload["detector"]),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class AnalysisResult:
    """Events and 28 parameters calculated for one walking segment."""

    schema_version: str
    metrics: dict[str, Any]
    events: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int | None = None) -> str:
        """序列化为 JSON；NaN 已在构建时转 None，因此 allow_nan=False 是安全的。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False, indent=indent)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AnalysisResult":
        return cls(
            schema_version=str(payload["schema_version"]),
            metrics=dict(payload["metrics"]),
            events=dict(payload["events"]),
            provenance=dict(payload["provenance"]),
        )
