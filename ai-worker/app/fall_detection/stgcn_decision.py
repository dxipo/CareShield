from __future__ import annotations

from dataclasses import dataclass

from app.fall_detection.detector import FallState


@dataclass(frozen=True, slots=True)
class STGCNDecision:
    state: FallState
    score: float
    state_changed: bool


class STGCNDecisionEngine:
    """Debounce uncalibrated STGCN scores without replacing the paper model."""

    def __init__(
        self,
        suspected_threshold: float = 0.60,
        fallen_threshold: float = 0.80,
        confirmation_windows: int = 3,
        recovery_windows: int = 5,
    ) -> None:
        if not 0 <= suspected_threshold <= fallen_threshold <= 1:
            raise ValueError("Invalid STGCN thresholds")
        self.suspected_threshold = suspected_threshold
        self.fallen_threshold = fallen_threshold
        self.confirmation_windows = confirmation_windows
        self.recovery_windows = recovery_windows
        self.reset()

    def reset(self) -> None:
        self.state = FallState.NORMAL
        self._fall_windows = 0
        self._normal_windows = 0

    def update(self, score: float) -> STGCNDecision:
        previous = self.state
        if score >= self.fallen_threshold:
            self._fall_windows += 1
            self._normal_windows = 0
            if self.state == FallState.NORMAL:
                self.state = FallState.SUSPECTED_FALL
            if self._fall_windows >= self.confirmation_windows:
                self.state = FallState.FALLEN
        elif score >= self.suspected_threshold:
            self._fall_windows = max(1, self._fall_windows)
            self._normal_windows = 0
            if self.state == FallState.NORMAL:
                self.state = FallState.SUSPECTED_FALL
            elif self.state == FallState.FALLEN:
                self.state = FallState.RECOVERING
        else:
            self._fall_windows = 0
            self._normal_windows += 1
            if self.state == FallState.SUSPECTED_FALL:
                self.state = FallState.NORMAL
            elif self.state == FallState.FALLEN:
                self.state = FallState.RECOVERING
            elif (
                self.state == FallState.RECOVERING
                and self._normal_windows >= self.recovery_windows
            ):
                self.state = FallState.NORMAL
        return STGCNDecision(
            state=self.state,
            score=max(0.0, min(1.0, score)),
            state_changed=self.state != previous,
        )
