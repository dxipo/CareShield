from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gaitkit.events import CachedEventDetector
from gaitkit.metrics import CANONICAL_METRICS
from gaitkit.pipeline import GaitPipeline
from synth import make_explicit_events, make_synthetic_walk


def test_pipeline_returns_exactly_28_finite_parameters() -> None:
    events = make_explicit_events()
    result = GaitPipeline(event_detector=CachedEventDetector(events)).analyse(make_synthetic_walk(), 1700.0)
    assert tuple(name for name in CANONICAL_METRICS if name in result.metrics) == CANONICAL_METRICS
    assert len(CANONICAL_METRICS) == 28
    assert all(np.isfinite(float(result.metrics[name])) for name in CANONICAL_METRICS)
    assert set(result.to_dict()) == {"schema_version", "metrics", "events", "provenance"}
