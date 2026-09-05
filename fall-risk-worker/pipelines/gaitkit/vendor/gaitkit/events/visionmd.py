"""流水线位置：事件检测层——VisionMD GaitTransformer 适配器。

VisionMD-Gait（GaitValidation 公开工作流）使用一个在 TF/JAX 上运行的
GaitTransformer 做步态相位估计，再经卡尔曼平滑解码出 HS/TO。这是视频骨架
（GVHMR/MotionBERT 路径）上的**首选事件检测器**；重型依赖全部懒加载，
缺失时 ``available()`` 返回 False 并给出安装提示，不影响 gaitkit 其余功能。

预处理四步必须与 VisionMD 公开 notebook 完全一致，否则相位输出失真
（移植自 smpl_pipeline/gait_validation.py:949-994，各步注释见下）：
1) 重采样到 30 Hz——GaitTransformer 的物理/模型位置跨度按 30 Hz、60 帧（2 s）
   窗口设计（60 Hz 视频的 120 帧窗口在 30 Hz 下的等价物），不是 90 帧演示默认值；
2) H36M-17 严格顺序堆叠为 [T,17,3]；
3) 逐帧做 17 关节质心中心化（notebook 的 frame-centre 约定）；
4) 轴变换 (x, y-up, z) -> (x, z, -y)，把 GVHMR 的 Y-up 换成模型期望的竖直轴约定。
"""

from __future__ import annotations

import logging

import numpy as np

from ..core.joints import H36M_17
from ..core.types import GaitEvents, Trajectory
from ..preprocess.temporal import resample_trajectory

logger = logging.getLogger(__name__)

_VISIONMD_HINT = (
    "VisionMD 事件解码器不可用：缺少 gait_transformer 包（TensorFlow/JAX）。\n"
    "请安装 GaitTransformer，并在 gaitkit.toml 中配置其仓库和 Python 环境。\n"
    "世界系轨迹也可以使用 gaitkit.events.AnalyticEventDetector 进行解析检测。"
)

# 相位通道重排：GaitTransformer 输出顺序 -> 卡尔曼平滑器期望顺序
# （移植自 smpl_pipeline/gait_validation.py:985）。
_PHASE_REORDER = (0, 4, 1, 5, 2, 6, 3, 7)


def visionmd_preprocess(points: np.ndarray, up_axis: int) -> np.ndarray:
    """对 [T,17,3] 堆叠点执行 VisionMD notebook 的坐标预处理（第 3、4 步）。

    移植自 smpl_pipeline/gait_validation.py:949-965（metrabs_ordered_for_visionmd）：
    先逐帧减去 17 关节质心，再按 up_axis 做轴交换——GVHMR (x, y-up, z) ->
    (x, z, -y)；Xsens 风格的 Z-up 输入恒等保留（仅诊断用途）。
    """
    points = points.copy()
    points -= np.mean(points, axis=1, keepdims=True)
    if up_axis == 1:
        points = points[:, :, [0, 2, 1]]
        points[:, :, 2] *= -1
    elif up_axis == 2:
        points = points[:, :, [0, 1, 2]]
    else:
        raise ValueError(f"不支持的竖直轴 {up_axis}")
    return points


class VisionMDEventDetector:
    """VisionMD-Gait/GaitTransformer 事件检测器（TF/JAX 懒加载）。

    参数:
        target_fps: 模型工作采样率（30 Hz）；
        window_frames: 步幅相位推理窗口 L（60 帧 = 2 s @30Hz）；
        use_xla: 首次跑通后可启用 TensorFlow XLA 加速。
    """

    name = "VisionMD-Gait/GaitTransformer"

    def __init__(self, *, target_fps: float = 30.0, window_frames: int = 60, use_xla: bool = False) -> None:
        self.target_fps = float(target_fps)
        self.window_frames = int(window_frames)
        self.use_xla = bool(use_xla)
        # A detector instance is reused for an entire batch.  Loading the
        # packaged Keras checkpoint for every walking segment is unnecessary
        # and makes batch inference several times slower.
        self._model = None

    def available(self) -> tuple[bool, str]:
        try:
            import gait_transformer  # noqa: F401
        except ImportError:
            try:
                from app.analysis.models.gait_transformer import gait_phase_kalman  # noqa: F401
                from app.analysis.models.gait_transformer import gait_phase_transformer_old  # noqa: F401
            except ImportError:
                return False, _VISIONMD_HINT
        return True, ""

    def detect(self, trajectory: Trajectory, height_mm: float) -> GaitEvents:
        """运行 GaitTransformer 相位推理 + 卡尔曼平滑，返回亚帧插值的事件时刻。

        完整流程（移植自 smpl_pipeline/gait_validation.py:968-994）：
        30 Hz 重采样 -> H36M-17 堆叠 -> 质心中心化 + 轴变换 ->
        load_default_model(pos_divider=None) -> gait_phase_stride_inference(L=60)
        -> 相位重排 [0,4,1,5,2,6,3,7] -> gait_kalman_smoother(dt=1/30) ->
        get_event_times（亚帧插值）。
        """
        bundled_runtime = False
        try:
            from gait_transformer.gait_phase_kalman import gait_kalman_smoother, get_event_times
            from gait_transformer.gait_phase_transformer import gait_phase_stride_inference, load_default_model
        except ImportError:
            try:
                from app.analysis.models.gait_transformer.gait_phase_kalman import (
                    gait_kalman_smoother,
                    get_event_times,
                )
                from app.analysis.models.gait_transformer.gait_phase_transformer_old import (
                    gait_phase_stride_inference,
                    load_default_model,
                )
                bundled_runtime = True
            except ImportError as error:
                raise RuntimeError(_VISIONMD_HINT) from error

        if abs(trajectory.fps - self.target_fps) > 0.1:
            sampled = resample_trajectory(trajectory, self.target_fps)
        else:
            sampled = trajectory
        missing = [name for name in H36M_17 if name not in sampled.joints]
        if missing:
            raise ValueError(
                f"{sampled.participant}-{sampled.view}: 缺少 VisionMD 所需 H36M 关节: {missing}"
            )
        points = np.stack([sampled.joints[name] for name in H36M_17], axis=1)
        points = visionmd_preprocess(points, sampled.up_axis)
        if self._model is None:
            self._model = load_default_model(pos_divider=None)
        model = self._model
        if bundled_runtime:
            phase, _ = gait_phase_stride_inference(
                points, height_mm, model, L=self.window_frames
            )
        else:
            phase, _ = gait_phase_stride_inference(
                points,
                height_mm,
                model,
                L=self.window_frames,
                use_xla=self.use_xla,
            )
        phase_ordered = np.take(phase, _PHASE_REORDER, axis=-1)
        state, _, _ = gait_kalman_smoother(phase_ordered, dt=1.0 / self.target_fps)
        result = get_event_times(state, sampled.time_s)
        logger.info("VisionMD events decoded: %d frames", len(sampled.time_s))
        return GaitEvents(
            left_down=np.asarray(result["left_down"], dtype=float),
            right_down=np.asarray(result["right_down"], dtype=float),
            left_up=np.asarray(result["left_up"], dtype=float),
            right_up=np.asarray(result["right_up"], dtype=float),
            detector=self.name,
        )
