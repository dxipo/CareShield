from __future__ import annotations

import os
from dataclasses import dataclass


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class FraudWorkerSettings:
    backend_internal_url: str
    media_relay_internal_url: str
    shared_token: str
    worker_id: str
    worker_version: str
    heartbeat_interval_seconds: float
    request_timeout_seconds: float
    enabled: bool
    audio_sample_rate: int
    audio_rms_threshold: float
    endpoint_silence_seconds: float
    minimum_utterance_seconds: float
    maximum_utterance_seconds: float
    reconnect_seconds: float
    asr_provider: str
    asr_model_path: str
    asr_device: str
    asr_compute_type: str
    asr_cpu_threads: int
    asr_num_workers: int
    asr_minimum_confidence: float
    llm_enabled: bool
    ollama_base_url: str
    ollama_model: str
    llm_timeout_seconds: float
    result_heartbeat_seconds: float
    transcript_retention_seconds: int


def load_settings() -> FraudWorkerSettings:
    return FraudWorkerSettings(
        backend_internal_url=os.getenv(
            "BACKEND_INTERNAL_URL", "http://backend:8000"
        ).strip().rstrip("/"),
        media_relay_internal_url=os.getenv(
            "MEDIA_RELAY_INTERNAL_URL", "http://media-relay:8095"
        ).strip().rstrip("/"),
        shared_token=os.getenv("AI_WORKER_SHARED_TOKEN", "").strip(),
        worker_id=os.getenv("FRAUD_WORKER_ID", "careshield-fraud-1").strip(),
        worker_version=os.getenv("FRAUD_WORKER_VERSION", "0.7.0").strip(),
        heartbeat_interval_seconds=float(
            os.getenv("AI_WORKER_HEARTBEAT_INTERVAL_SECONDS", "10")
        ),
        request_timeout_seconds=float(os.getenv("FRAUD_REQUEST_TIMEOUT_SECONDS", "10")),
        enabled=_boolean("FRAUD_DETECTION_ENABLED", True),
        audio_sample_rate=int(os.getenv("FRAUD_AUDIO_SAMPLE_RATE", "16000")),
        audio_rms_threshold=float(os.getenv("FRAUD_AUDIO_RMS_THRESHOLD", "180")),
        endpoint_silence_seconds=float(
            os.getenv("FRAUD_ENDPOINT_SILENCE_SECONDS", "0.7")
        ),
        minimum_utterance_seconds=float(
            os.getenv("FRAUD_MINIMUM_UTTERANCE_SECONDS", "0.5")
        ),
        maximum_utterance_seconds=float(
            os.getenv("FRAUD_MAXIMUM_UTTERANCE_SECONDS", "15")
        ),
        reconnect_seconds=float(os.getenv("FRAUD_RECONNECT_SECONDS", "3")),
        asr_provider=os.getenv("FRAUD_ASR_PROVIDER", "faster_whisper").strip(),
        asr_model_path=os.getenv(
            "FRAUD_ASR_MODEL_PATH", "/models/fraud/whisper-model"
        ).strip(),
        asr_device=os.getenv("FRAUD_ASR_DEVICE", "cpu").strip(),
        asr_compute_type=os.getenv("FRAUD_ASR_COMPUTE_TYPE", "int8").strip(),
        asr_cpu_threads=max(1, int(os.getenv("FRAUD_ASR_CPU_THREADS", "2"))),
        asr_num_workers=max(1, int(os.getenv("FRAUD_ASR_NUM_WORKERS", "1"))),
        asr_minimum_confidence=float(
            os.getenv("FRAUD_ASR_MINIMUM_CONFIDENCE", "0.50")
        ),
        llm_enabled=_boolean("FRAUD_LLM_ENABLED", True),
        ollama_base_url=os.getenv(
            "FRAUD_OLLAMA_BASE_URL", "http://ollama:11434"
        ).strip().rstrip("/"),
        ollama_model=os.getenv("FRAUD_OLLAMA_MODEL", "qwen3:4b").strip(),
        llm_timeout_seconds=float(os.getenv("FRAUD_LLM_TIMEOUT_SECONDS", "20")),
        result_heartbeat_seconds=float(
            os.getenv("FRAUD_RESULT_HEARTBEAT_SECONDS", "5")
        ),
        transcript_retention_seconds=int(
            os.getenv("FRAUD_TRANSCRIPT_RETENTION_SECONDS", "60")
        ),
    )
