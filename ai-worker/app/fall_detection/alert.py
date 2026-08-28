from __future__ import annotations

from app.fall_detection.detector import FallState


class FallAlertLatch:
    """Keep a confirmed fall visible until an operator acknowledges it.

    Acknowledgement silences only the current incident. A later confirmed fall
    can open a new alert after the detector has returned to NORMAL.
    """

    def __init__(self) -> None:
        self.active = False
        self.acknowledged = False
        self._incident_open = False

    def update(self, state: FallState) -> None:
        if state is FallState.FALLEN:
            if not self._incident_open:
                self._incident_open = True
                self.acknowledged = False
            if not self.acknowledged:
                self.active = True
        elif state is FallState.NORMAL and self._incident_open:
            self._incident_open = False
            self.active = False
            self.acknowledged = False

    def acknowledge(self) -> None:
        if self._incident_open:
            self.active = False
            self.acknowledged = True

    def reset(self) -> None:
        self.active = False
        self.acknowledged = False
        self._incident_open = False
