from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from careshield_contracts import AlgorithmResult, AlgorithmTask, RiskLevel

from app.asr.faster_whisper import AsrError, FasterWhisperAsr, is_transcript_usable
from app.core.config import FraudWorkerSettings
from app.detection.detector import FraudDetector, redact_transcript
from app.llm.ollama import OllamaAdjudicator
from app.media.audio_reader import AudioReader, AudioReaderError
from app.media.segmenter import EndpointSegmenter, Utterance
from app.publisher.result_publisher import PublishError, ResultPublisher


logger = logging.getLogger(__name__)


class FraudDetectionService:
    def __init__(
        self,
        settings: FraudWorkerSettings,
        publisher: ResultPublisher,
    ) -> None:
        self.settings = settings
        self.publisher = publisher
        self.reader = AudioReader(settings)
        self.asr = FasterWhisperAsr(
            settings.asr_model_path,
            settings.asr_device,
            settings.asr_compute_type,
            settings.asr_cpu_threads,
            settings.asr_num_workers,
        )
        self.detector = FraudDetector(settings.transcript_retention_seconds)
        self.llm = (
            OllamaAdjudicator(
                settings.ollama_base_url,
                settings.ollama_model,
                settings.llm_timeout_seconds,
            )
            if settings.llm_enabled
            else None
        )
        self.status = "disabled" if not settings.enabled else "starting"
        self.audio_status = "not_connected"
        self.asr_status = "not_loaded"
        self.last_error: str | None = None
        self.last_transcript_at: datetime | None = None
        self.last_result_at: datetime | None = None
        self.last_asr_latency_ms: float | None = None
        self.last_utterance_seconds: float | None = None
        self.reconnect_count = 0
        self.processed_utterances = 0
        self._dialogue: deque[tuple[float, str]] = deque(maxlen=8)
        self._task: asyncio.Task | None = None
        self._stop = threading.Event()

    @property
    def capability(self) -> str:
        if not self.settings.enabled:
            return "not_installed"
        if self.status in {"runtime_error", "asr_error"}:
            return "error"
        if self.status in {"starting", "loading_asr"}:
            return "starting"
        if self.audio_status != "connected":
            return "unavailable"
        return "running"

    async def start(self) -> None:
        if not self.settings.enabled or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="fraud-detection")

    async def stop(self) -> None:
        self._stop.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.reader.close()
        if self.llm is not None:
            self.llm.close()

    def runtime_metadata(self) -> dict:
        llm_ready = self.llm.ready() if self.llm is not None else False
        return {
            "fraud_detection": {
                "status": self.status,
                "audio_status": self.audio_status,
                "audio_sample_rate": self.settings.audio_sample_rate,
                "asr_provider": self.settings.asr_provider,
                "asr_status": self.asr_status,
                "asr_device": self.settings.asr_device,
                "asr_cpu_threads": self.settings.asr_cpu_threads,
                "asr_num_workers": self.settings.asr_num_workers,
                "llm_provider": "ollama" if self.llm is not None else "disabled",
                "llm_model": self.settings.ollama_model if self.llm is not None else None,
                "llm_ready": llm_ready,
                "detector_state": self.detector.state,
                "processed_utterances": self.processed_utterances,
                "last_transcript_at": (
                    self.last_transcript_at.isoformat() if self.last_transcript_at else None
                ),
                "last_result_at": (
                    self.last_result_at.isoformat() if self.last_result_at else None
                ),
                "last_asr_latency_ms": self.last_asr_latency_ms,
                "last_utterance_seconds": self.last_utterance_seconds,
                "reconnect_count": self.reconnect_count,
                "last_error": self.last_error,
            }
        }

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                self.status = "loading_asr"
                await asyncio.to_thread(self.asr.load)
                self.asr_status = "ready"
                self.status = "listening"
                self.audio_status = "connecting"
                await asyncio.to_thread(self._consume_stream, loop)
                raise AudioReaderError("Shared camera audio ended")
            except asyncio.CancelledError:
                raise
            except AsrError as exc:
                self.status = "asr_error"
                self.asr_status = "error"
                self.last_error = str(exc)
            except AudioReaderError as exc:
                self.status = "media_reconnecting"
                self.audio_status = "reconnecting"
                self.last_error = str(exc)
                self.reconnect_count += 1
            except Exception:
                self.status = "runtime_error"
                self.last_error = "Fraud detection runtime failed"
                logger.exception("Fraud detection runtime failed without sensitive media data")
            await asyncio.sleep(self.settings.reconnect_seconds)

    def _consume_stream(self, loop: asyncio.AbstractEventLoop) -> None:
        segmenter = EndpointSegmenter(
            sample_rate=self.settings.audio_sample_rate,
            rms_threshold=self.settings.audio_rms_threshold,
            endpoint_silence_seconds=self.settings.endpoint_silence_seconds,
            minimum_utterance_seconds=self.settings.minimum_utterance_seconds,
            maximum_utterance_seconds=self.settings.maximum_utterance_seconds,
        )
        self.audio_status = "connected"
        self.status = "listening"
        self.last_error = None
        for chunk in self.reader.chunks():
            if self._stop.is_set():
                return
            utterance = segmenter.feed(chunk.pcm_s16le)
            if utterance is not None:
                self._process_utterance(utterance, chunk.timestamp, loop)

    def _process_utterance(
        self,
        utterance: Utterance,
        source_timestamp: datetime,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        transcript = self.asr.transcribe(
            utterance.pcm_s16le,
            self.settings.audio_sample_rate,
        )
        self.last_asr_latency_ms = transcript.latency_ms
        self.last_utterance_seconds = utterance.duration_seconds
        if not is_transcript_usable(
            transcript.text,
            transcript.confidence,
            self.settings.asr_minimum_confidence,
        ):
            return

        now = time.monotonic()
        self._dialogue.append((now, transcript.text))
        while self._dialogue and now - self._dialogue[0][0] > self.settings.transcript_retention_seconds:
            self._dialogue.popleft()
        self.last_transcript_at = datetime.now(timezone.utc)
        self.processed_utterances += 1

        llm_result = None
        if self.llm is not None and self._is_llm_candidate(transcript.text):
            dialogue = " ".join(text for _, text in self._dialogue)
            llm_result = self.llm.judge(dialogue)
        decision = self.detector.analyze(transcript.text, llm=llm_result)
        result_timestamp = datetime.now(timezone.utc)
        result = AlgorithmResult(
            result_id=uuid4(),
            task=AlgorithmTask.FRAUD_DETECTION,
            model_id="careshield-fraud-ensemble",
            model_version="m7-v1",
            device_id=self.reader.device_id,
            source_timestamp=source_timestamp,
            result_timestamp=result_timestamp,
            label=decision.state,
            score=decision.score,
            level={
                "normal": RiskLevel.NORMAL,
                "suspicious": RiskLevel.MEDIUM,
                "warning": RiskLevel.HIGH,
                "critical": RiskLevel.CRITICAL,
            }[decision.state],
            latency_ms=max(
                0.0,
                (result_timestamp - source_timestamp).total_seconds() * 1000,
            ),
            metadata={
                "score_type": "heuristic_ensemble",
                "audio_source": "careshield_media_relay",
                "asr_provider": self.settings.asr_provider,
                "asr_confidence": transcript.confidence,
                "asr_latency_ms": transcript.latency_ms,
                "utterance_seconds": utterance.duration_seconds,
                "transcript_preview": redact_transcript(transcript.text),
                "evidence_categories": list(decision.evidence_categories),
                "matched_terms": list(decision.matched_terms),
                "llm_used": decision.llm_used,
                "llm_reason": (
                    redact_transcript(decision.llm_reason)
                    if decision.llm_reason
                    else None
                ),
                "alert_active": decision.alert_active,
            },
            simulated=False,
        )
        future = asyncio.run_coroutine_threadsafe(self.publisher.publish(result), loop)
        try:
            future.result(timeout=self.settings.request_timeout_seconds + 2)
            self.last_result_at = result_timestamp
            self.last_error = None
        except (PublishError, TimeoutError):
            self.last_error = "Fraud result delivery failed"

    @staticmethod
    def _is_llm_candidate(text: str) -> bool:
        # Local inference is privacy-preserving and fast enough for segmented
        # utterances. Review meaningful language even when ASR misspells the
        # exact rule keyword; skip only very short acknowledgement/filler text.
        compact = text.strip()
        return len(compact) >= 4 and compact not in {
            "好的好的",
            "谢谢谢谢",
            "知道了吧",
        }
