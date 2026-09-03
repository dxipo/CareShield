from __future__ import annotations

from dataclasses import dataclass


class AsrError(RuntimeError):
    """Speech recognition failure without raw audio or transcript content."""


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str | None
    confidence: float | None
    latency_ms: float


def is_transcript_usable(
    text: str,
    confidence: float | None,
    minimum_confidence: float,
) -> bool:
    return len(text) >= 2 and (
        confidence is None or confidence >= minimum_confidence
    )
