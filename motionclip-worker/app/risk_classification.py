"""Deterministic research risk grading for healthy-reference distance."""

from __future__ import annotations

import json
from pathlib import Path


def load_risk_thresholds(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    thresholds = payload.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("Risk threshold configuration is invalid")
    low_medium = float(thresholds["low_medium"])
    medium_high = float(thresholds["medium_high"])
    if not 0 <= low_medium < medium_high <= 2:
        raise ValueError("Risk thresholds must be ordered within [0,2]")
    return {
        **payload,
        "thresholds": {
            "low_medium": low_medium,
            "medium_high": medium_high,
        },
    }


def classify_risk(distance: float, thresholds: dict[str, float]) -> str:
    value = float(distance)
    if value < thresholds["low_medium"]:
        return "low"
    if value < thresholds["medium_high"]:
        return "medium"
    return "high"
