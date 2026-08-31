import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from careshield_contracts import AlgorithmResult, AlgorithmTask
from app.core.config import FraudWorkerSettings
from app.publisher.result_publisher import ResultPublisher


def settings() -> FraudWorkerSettings:
    return FraudWorkerSettings(
        backend_internal_url="http://backend.test",
        media_relay_internal_url="http://relay.test",
        shared_token="internal-test-token",
        worker_id="fraud-test",
        worker_version="test",
        heartbeat_interval_seconds=10,
        request_timeout_seconds=2,
        enabled=True,
        audio_sample_rate=16000,
        audio_rms_threshold=180,
        endpoint_silence_seconds=0.7,
        minimum_utterance_seconds=0.5,
        maximum_utterance_seconds=15,
        reconnect_seconds=1,
        asr_provider="faster_whisper",
        asr_model_path="/models/test",
        asr_device="cpu",
        asr_compute_type="int8",
        asr_cpu_threads=2,
        asr_num_workers=1,
        asr_minimum_confidence=0.5,
        llm_enabled=False,
        ollama_base_url="http://ollama.test",
        ollama_model="test",
        llm_timeout_seconds=2,
        result_heartbeat_seconds=5,
        transcript_retention_seconds=60,
    )


def test_publisher_uses_internal_auth_and_canonical_contract() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer internal-test-token"
            assert request.url.path == "/internal/ai/results"
            return httpx.Response(204)

        publisher = ResultPublisher(settings(), transport=httpx.MockTransport(handler))
        await publisher.publish(
            AlgorithmResult(
                result_id=uuid4(),
                task=AlgorithmTask.FRAUD_DETECTION,
                model_id="fraud-test",
                model_version="test",
                result_timestamp=datetime.now(timezone.utc),
                label="normal",
                score=0,
                level="normal",
                simulated=False,
            )
        )
        await publisher.close()

    asyncio.run(run())
