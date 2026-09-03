from __future__ import annotations

from app.asr.faster_whisper import FasterWhisperAsr
from app.asr.sensevoice import SenseVoiceSmallAsr
from app.core.config import FraudWorkerSettings


def build_asr(settings: FraudWorkerSettings):
    provider = settings.asr_provider.lower().replace("-", "_")
    if provider in {"sensevoice", "sensevoice_small", "funasr_sensevoice"}:
        return SenseVoiceSmallAsr(
            settings.asr_model_path,
            settings.asr_device,
            settings.asr_cpu_threads,
        )
    if provider == "faster_whisper":
        return FasterWhisperAsr(
            settings.asr_model_path,
            settings.asr_device,
            settings.asr_compute_type,
            settings.asr_cpu_threads,
            settings.asr_num_workers,
        )
    raise ValueError(f"Unsupported ASR provider: {settings.asr_provider}")
