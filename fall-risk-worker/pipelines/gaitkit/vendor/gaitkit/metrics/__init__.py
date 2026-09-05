"""指标层：28 项步态参数的注册表、分组模块与统一计算入口。"""

from .registry import (
    CANONICAL_METRICS,
    CORE8,
    METRIC_REGISTRY,
    RISK_EXT20,
    XSENS_COMPARABLE21,
    MetricContext,
    MetricDef,
    build_context,
    compute_all,
    metric_manifest,
)

__all__ = [
    "MetricDef",
    "MetricContext",
    "METRIC_REGISTRY",
    "CANONICAL_METRICS",
    "CORE8",
    "RISK_EXT20",
    "XSENS_COMPARABLE21",
    "build_context",
    "compute_all",
    "metric_manifest",
]
