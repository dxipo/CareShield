from app.fall_detection.detector import FallDecision


class FallPublishPolicy:
    def __init__(self, heartbeat_seconds: float, significant_score_delta: float) -> None:
        self.heartbeat_seconds = heartbeat_seconds
        self.significant_score_delta = significant_score_delta
        self._last_timestamp: float | None = None
        self._last_score: float | None = None

    def should_publish(self, decision: FallDecision, timestamp_seconds: float) -> bool:
        due = (
            self._last_timestamp is None
            or timestamp_seconds - self._last_timestamp >= self.heartbeat_seconds
        )
        changed = (
            self._last_score is None
            or abs(decision.score - self._last_score) >= self.significant_score_delta
        )
        if decision.state_changed or due or changed:
            self._last_timestamp = timestamp_seconds
            self._last_score = decision.score
            return True
        return False

    def reset(self) -> None:
        self._last_timestamp = None
        self._last_score = None
