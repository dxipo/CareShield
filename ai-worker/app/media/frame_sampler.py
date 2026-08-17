class FrameSampler:
    """Monotonic time sampler that keeps source and inference rates distinct."""

    def __init__(self, target_fps: float) -> None:
        if target_fps <= 0:
            raise ValueError("target_fps must be positive")
        self.target_fps = target_fps
        self._minimum_interval = 1.0 / target_fps
        self._last_sampled_at: float | None = None

    def should_sample(self, timestamp_seconds: float) -> bool:
        if (
            self._last_sampled_at is not None
            and timestamp_seconds < self._last_sampled_at
        ):
            self.reset()
        if (
            self._last_sampled_at is None
            or timestamp_seconds - self._last_sampled_at >= self._minimum_interval * 0.95
        ):
            self._last_sampled_at = timestamp_seconds
            return True
        return False

    def reset(self) -> None:
        self._last_sampled_at = None
