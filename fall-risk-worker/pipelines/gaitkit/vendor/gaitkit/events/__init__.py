"""事件检测层：检测器协议与两个实现（解析式 / VisionMD GaitTransformer）。"""

from .analytic import AnalyticEventDetector
from .base import EventDetector
from .cached import CachedEventDetector
from .visionmd import VisionMDEventDetector, visionmd_preprocess

__all__ = [
    "EventDetector",
    "AnalyticEventDetector",
    "CachedEventDetector",
    "VisionMDEventDetector",
    "visionmd_preprocess",
]
