from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

import numpy as np

from app.asr.contracts import AsrError, Transcript


class SenseVoiceSmallAsr:
    """Local Chinese ASR and ITN using the official FunASR ONNX runtime."""

    def __init__(
        self,
        model_path: str,
        device: str,
        cpu_threads: int = 2,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.cpu_threads = max(1, cpu_threads)
        self._model = None
        self._postprocess: Callable[[str], str] | None = None
        self.load_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        if not os.path.isfile(os.path.join(self.model_path, "model_quant.onnx")):
            self.load_error = "SenseVoiceSmall model directory is not configured"
            raise AsrError(self.load_error)
        try:
            from funasr_onnx import SenseVoiceSmall
            from funasr_onnx.utils.postprocess_utils import (
                rich_transcription_postprocess,
            )

            device_id = "-1" if self.device.lower() == "cpu" else "0"
            self._model = SenseVoiceSmall(
                self.model_path,
                batch_size=1,
                device_id=device_id,
                quantize=True,
                intra_op_num_threads=self.cpu_threads,
            )
            self._postprocess = rich_transcription_postprocess
            self.load_error = None
        except Exception as exc:
            self.load_error = "SenseVoiceSmall model could not be loaded"
            raise AsrError(self.load_error) from exc

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> Transcript:
        if not self.ready:
            self.load()
        if sample_rate != 16_000:
            raise AsrError("ASR input must be 16 kHz mono PCM")
        audio = np.frombuffer(pcm_s16le, dtype=np.int16).astype(np.float32)
        audio /= 32768.0
        started = time.perf_counter()
        try:
            results = self._model(audio, language="zh", textnorm="withitn")
            raw_text = results[0] if results else ""
            text = self._postprocess(raw_text) if self._postprocess else raw_text
        except Exception as exc:
            raise AsrError("Speech recognition failed") from exc
        text = re.sub(r"\s+", "", str(text)).strip()
        return Transcript(
            text=text,
            language="zh",
            # The ONNX wrapper does not expose a calibrated utterance score.
            confidence=None,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
