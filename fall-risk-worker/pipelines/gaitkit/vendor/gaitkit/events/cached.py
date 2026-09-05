"""预计算事件适配器：支持把 GaitTransformer 推理与轻量参数计算分环境运行。"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.types import GaitEvents, Trajectory


@dataclass(frozen=True)
class CachedEventDetector:
    """把已经落盘/加载的 HS、TO 事件注入分析流水线。

    GaitTransformer 往往运行在独立的 TensorFlow/JAX 环境中。调用方先用
    ``load_events`` 读取其 NPZ，再构造本适配器，即可在普通 gaitkit 环境中
    完成确定性双路线融合。事件会自动裁剪到当前轨迹窗口。
    """

    events: GaitEvents
    name: str = "cached-events"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def detect(self, trajectory: Trajectory, height_mm: float) -> GaitEvents:
        del height_mm
        selected = self.events.in_window(float(trajectory.time_s[0]), float(trajectory.time_s[-1]))
        return GaitEvents(
            selected.left_down,
            selected.right_down,
            selected.left_up,
            selected.right_up,
            detector=f"{self.name}:{self.events.detector}",
            metadata={**selected.metadata, "cached_event_source": self.events.detector},
        )
