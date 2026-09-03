from __future__ import annotations

import os
import re
import time

import numpy as np

from app.asr.contracts import AsrError, Transcript, is_transcript_usable


__all__ = ["AsrError", "FasterWhisperAsr", "Transcript", "is_transcript_usable"]


class FasterWhisperAsr:
    def __init__(
        self,
        model_path: str,
        device: str,
        compute_type: str,
        cpu_threads: int = 2,
        num_workers: int = 1,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = max(1, cpu_threads)
        self.num_workers = max(1, num_workers)
        self._model = None
        self.load_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        if not os.path.isdir(self.model_path):
            self.load_error = "ASR model directory is not configured"
            raise AsrError(self.load_error)
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_path,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                num_workers=self.num_workers,
                local_files_only=True,
            )
            self.load_error = None
        except Exception as exc:
            self.load_error = "ASR model could not be loaded"
            raise AsrError(self.load_error) from exc

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> Transcript:
        if not self.ready:
            self.load()
        samples = np.frombuffer(pcm_s16le, dtype=np.int16).astype(np.float32)
        if sample_rate != 16_000:
            raise AsrError("ASR input must be 16 kHz mono PCM")
        audio = samples / 32768.0
        started = time.perf_counter()
        try:
            segments, info = self._model.transcribe(
                audio,
                language="zh",
                beam_size=3,
                vad_filter=False,
                condition_on_previous_text=False,
                temperature=0.0,
            )
            materialized = list(segments)
        except Exception as exc:
            raise AsrError("Speech recognition failed") from exc
        text = re.sub(r"\s+", "", "".join(item.text for item in materialized)).strip()
        probabilities = [
            float(np.exp(item.avg_logprob))
            for item in materialized
            if item.avg_logprob is not None
        ]
        confidence = (
            max(0.0, min(1.0, float(np.mean(probabilities))))
            if probabilities
            else None
        )
        return Transcript(
            text=text,
            language=getattr(info, "language", None),
            confidence=confidence,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
