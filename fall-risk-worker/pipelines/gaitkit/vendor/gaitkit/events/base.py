"""流水线位置：事件检测层——检测器协议。

事件检测是"时间上把步态切成周期"的一步，与"在空间上测量步态参数"刻意分离
（这一分离原则继承自 smpl_pipeline：Xsens 参考用解析法，视频骨架用
VisionMD GaitTransformer，两者产出同一 GaitEvents 契约）。

任何实现 ``EventDetector`` 协议的对象都可注入 ``GaitPipeline``：
``available()`` 用于在重型依赖（TF/JAX）缺失时提前给出可操作提示，
``detect()`` 返回秒级事件时刻。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.types import GaitEvents, Trajectory


@runtime_checkable
class EventDetector(Protocol):
    """步态事件检测器协议。

    实现约定：

    - ``name``：写入 provenance 的稳定标识符；
    - ``available()``：返回 (是否可用, 不可用时的安装/环境提示)；
    - ``detect(trajectory, height_mm)``：在传入片段上检测事件，返回秒级时刻；
      输入轨迹已由 pipeline 重采样到 target_fps（通常 30 Hz）。
    """

    name: str

    def available(self) -> tuple[bool, str]:
        ...

    def detect(self, trajectory: Trajectory, height_mm: float) -> GaitEvents:
        ...
