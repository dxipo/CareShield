from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from app.fall_detection.pose import PosePerson, pose_is_reliable


@dataclass(frozen=True, slots=True)
class _PoseObservation:
    timestamp_seconds: float
    points: np.ndarray
    point_validity: np.ndarray
    frame_valid: bool


class PoseSequenceStore:
    """Resample a short real-time window into the published model contract.

    The camera remains approximately 15 FPS. A two-second window therefore
    contains about 30 real observations, which are linearly interpolated to the
    75 observed frames consumed by STGCN-Extend. Its decoder generates the
    remaining 25 frames. Interpolation aligns time; it creates no new evidence.
    """

    def __init__(
        self,
        observed_length: int = 75,
        model_length: int = 100,
        window_seconds: float = 2.0,
        minimum_confidence: float = 0.35,
    ) -> None:
        if observed_length != 75 or model_length != 100:
            raise ValueError("STGCN-Extend requires 75 observed and 25 predicted frames")
        if window_seconds <= 0:
            raise ValueError("Pose observation window must be positive")
        self.observed_length = observed_length
        self.model_length = model_length
        self.window_seconds = window_seconds
        self.minimum_confidence = minimum_confidence
        self._buffers: dict[str, deque[_PoseObservation]] = {}

    def update(
        self,
        persons: tuple[PosePerson, ...],
        active_track_ids: tuple[str, ...],
        timestamp_seconds: float,
    ) -> None:
        visible = {person.person_id: person for person in persons}
        for track_id in active_track_ids:
            buffer = self._buffers.setdefault(track_id, deque())
            person = visible.get(track_id)
            points, point_validity = self._pose_array(person)
            buffer.append(
                _PoseObservation(
                    timestamp_seconds=timestamp_seconds,
                    points=points,
                    point_validity=point_validity,
                    frame_valid=(
                        person is not None
                        and pose_is_reliable(person, self.minimum_confidence)
                    ),
                )
            )
            self._prune(buffer, timestamp_seconds)

        for track_id in tuple(self._buffers):
            if track_id not in active_track_ids:
                self._buffers.pop(track_id, None)

    def ready(self, track_id: str) -> bool:
        buffer = self._buffers.get(track_id)
        return bool(
            buffer
            and len(buffer) >= 2
            and buffer[-1].timestamp_seconds - buffer[0].timestamp_seconds
            >= self.window_seconds * 0.98
        )

    def progress(self, track_id: str) -> float:
        buffer = self._buffers.get(track_id)
        if not buffer or len(buffer) < 2:
            return 0.0
        elapsed = buffer[-1].timestamp_seconds - buffer[0].timestamp_seconds
        return min(1.0, max(0.0, elapsed / self.window_seconds))

    def tensor(self, track_id: str) -> np.ndarray:
        if not self.ready(track_id):
            raise ValueError("Pose sequence is still warming up")
        buffer = self._buffers[track_id]
        end = buffer[-1].timestamp_seconds
        target_times = np.linspace(
            end - self.window_seconds,
            end,
            self.observed_length,
            dtype=np.float64,
        )
        observed = np.zeros((self.observed_length, 17, 2), dtype=np.float32)
        for keypoint_index in range(17):
            valid = [item for item in buffer if item.point_validity[keypoint_index]]
            if len(valid) < 2:
                continue
            source_times = np.asarray(
                [item.timestamp_seconds for item in valid],
                dtype=np.float64,
            )
            inside = (target_times >= source_times[0]) & (target_times <= source_times[-1])
            if not inside.any():
                continue
            for coordinate in range(2):
                source_values = np.asarray(
                    [item.points[keypoint_index, coordinate] for item in valid],
                    dtype=np.float32,
                )
                observed[inside, keypoint_index, coordinate] = np.interp(
                    target_times[inside],
                    source_times,
                    source_values,
                )

        sequence = np.zeros((self.model_length, 17, 2), dtype=np.float32)
        sequence[: self.observed_length] = observed
        return sequence[np.newaxis, np.newaxis, ...]

    def valid_ratio(self, track_id: str) -> float:
        buffer = self._buffers.get(track_id)
        if not buffer:
            return 0.0
        end = buffer[-1].timestamp_seconds
        window = [
            item
            for item in buffer
            if item.timestamp_seconds >= end - self.window_seconds
        ]
        return sum(item.frame_valid for item in window) / len(window) if window else 0.0

    def reset(self) -> None:
        self._buffers.clear()

    def _prune(
        self,
        buffer: deque[_PoseObservation],
        timestamp_seconds: float,
    ) -> None:
        cutoff = timestamp_seconds - self.window_seconds - 0.25
        while len(buffer) > 2 and buffer[1].timestamp_seconds < cutoff:
            buffer.popleft()

    def _pose_array(
        self,
        person: PosePerson | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        points = np.zeros((17, 2), dtype=np.float32)
        validity = np.zeros(17, dtype=np.bool_)
        if person is None:
            return points, validity
        for index, point in enumerate(person.keypoints[:17]):
            if point.confidence < self.minimum_confidence:
                continue
            # Training PreNormalize2D maps image coordinates to [-1, 1].
            points[index, 0] = point.x * 2.0 - 1.0
            points[index, 1] = point.y * 2.0 - 1.0
            validity[index] = True
        return points, validity
