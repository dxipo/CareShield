"""Gaitkit: RGB video to 28 gait parameters."""

from .config import GaitKitConfig
from .core import AnalysisResult, GaitEvents, Trajectory
from .events import AnalyticEventDetector, CachedEventDetector, EventDetector, VisionMDEventDetector
from .io import load_hmr4d_results, load_joint_npz, load_trajectory, save_events, save_trajectory
from .metrics import CANONICAL_METRICS, CORE8, METRIC_REGISTRY, RISK_EXT20, MetricDef, compute_all, metric_manifest
from .pipeline import GaitPipeline

__version__ = "2.0.0"

__all__ = [
    "__version__", "GaitKitConfig", "Trajectory", "GaitEvents", "AnalysisResult",
    "EventDetector", "AnalyticEventDetector", "CachedEventDetector", "VisionMDEventDetector",
    "save_trajectory", "load_trajectory", "save_events", "load_hmr4d_results", "load_joint_npz",
    "MetricDef", "METRIC_REGISTRY", "CANONICAL_METRICS", "CORE8", "RISK_EXT20",
    "compute_all", "metric_manifest", "GaitPipeline",
]
