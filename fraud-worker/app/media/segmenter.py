from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Utterance:
    pcm_s16le: bytes
    duration_seconds: float
    peak_rms: float


class EndpointSegmenter:
    """Small deterministic energy gate with bounded memory and trailing silence."""

    def __init__(
        self,
        *,
        sample_rate: int,
        rms_threshold: float,
        endpoint_silence_seconds: float,
        minimum_utterance_seconds: float,
        maximum_utterance_seconds: float,
    ) -> None:
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self.endpoint_samples = int(endpoint_silence_seconds * sample_rate)
        self.minimum_samples = int(minimum_utterance_seconds * sample_rate)
        self.maximum_samples = int(maximum_utterance_seconds * sample_rate)
        self.preroll_samples = min(self.minimum_samples, sample_rate // 2)
        self._samples = np.empty(0, dtype=np.int16)
        self._speech_seen = False
        self._silence_samples = 0
        self._peak_rms = 0.0

    def feed(self, pcm_s16le: bytes) -> Utterance | None:
        incoming = np.frombuffer(pcm_s16le, dtype=np.int16)
        if incoming.size == 0:
            return None
        values = incoming.astype(np.float32)
        rms = float(np.sqrt(np.mean(values * values)))
        self._peak_rms = max(self._peak_rms, rms)
        self._samples = np.concatenate((self._samples, incoming))

        if rms >= self.rms_threshold:
            self._speech_seen = True
            self._silence_samples = 0
        elif self._speech_seen:
            self._silence_samples += incoming.size

        if not self._speech_seen:
            self._samples = self._samples[-self.preroll_samples :]
            return None

        complete = self._silence_samples >= self.endpoint_samples
        forced = self._samples.size >= self.maximum_samples
        if not complete and not forced:
            return None
        return self._finish()

    def flush(self) -> Utterance | None:
        if not self._speech_seen:
            self.reset()
            return None
        return self._finish()

    def reset(self) -> None:
        self._samples = np.empty(0, dtype=np.int16)
        self._speech_seen = False
        self._silence_samples = 0
        self._peak_rms = 0.0

    def _finish(self) -> Utterance | None:
        samples = self._samples
        peak = self._peak_rms
        self.reset()
        if samples.size < self.minimum_samples:
            return None
        return Utterance(
            pcm_s16le=samples.tobytes(),
            duration_seconds=samples.size / self.sample_rate,
            peak_rms=peak,
        )
