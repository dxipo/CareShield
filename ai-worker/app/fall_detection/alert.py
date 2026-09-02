from __future__ import annotations

import time
from collections.abc import Callable

from app.fall_detection.detector import FallState


class FallAlertLatch:
    """Keep a confirmed fall visible for a minimum operator-response window.

    Acknowledgement silences the current incident immediately. Automatic recovery
    cannot close an unacknowledged alert before the minimum visibility interval.
    A later confirmed fall can open a new alert after the detector returns to
    NORMAL.
    """

    def __init__(
        self,
        minimum_visible_seconds: float = 15.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if minimum_visible_seconds < 0:
            raise ValueError("minimum_visible_seconds cannot be negative")
        self.minimum_visible_seconds = minimum_visible_seconds
        self._clock = clock
        self.active = False
        self.acknowledged = False
        self._incident_open = False
        self._opened_at: float | None = None

    def update(self, state: FallState) -> None:
        if state is FallState.FALLEN:
            if not self._incident_open:
                self._incident_open = True
                self.acknowledged = False
                self._opened_at = self._clock()
            if not self.acknowledged:
                self.active = True
        elif state is FallState.NORMAL and self._incident_open:
            if (
                not self.acknowledged
                and self._opened_at is not None
                and self._clock() - self._opened_at < self.minimum_visible_seconds
            ):
                return
            self._incident_open = False
            self.active = False
            self.acknowledged = False
            self._opened_at = None

    def acknowledge(self) -> None:
        if self._incident_open:
            self.active = False
            self.acknowledged = True

    def reset(self) -> None:
        self.active = False
        self.acknowledged = False
        self._incident_open = False
        self._opened_at = None
