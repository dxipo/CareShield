import asyncio
import json

import httpx

from app.core.config import WorkerSettings
from app.publisher.result_publisher import ResultPublisher
from app.services.pipeline_test_service import PipelineTestService


def settings() -> WorkerSettings:
    return WorkerSettings(
        app_env="development",
        backend_internal_url="http://backend.test",
        shared_token="private-test-token",
        worker_id="worker-test",
        worker_version="0.4.0",
        heartbeat_interval_seconds=10,
        request_timeout_seconds=5,
    )


def test_result_publisher_sends_contract_and_internal_auth() -> None:
    async def run() -> None:
        captured = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "accepted"})

        publisher = ResultPublisher(settings(), transport=httpx.MockTransport(handler))
        try:
            result = PipelineTestService.build_result()
            await publisher.publish(result)
        finally:
            await publisher.close()

        assert captured["authorization"] == "Bearer private-test-token"
        assert captured["payload"]["task"] == "pipeline_test"
        assert captured["payload"]["simulated"] is True
        assert captured["payload"]["score"] is None

    asyncio.run(run())


def test_pipeline_test_is_always_simulated() -> None:
    result = PipelineTestService.build_result()
    assert result.simulated is True
    assert result.task.value == "pipeline_test"
    assert result.device_id is None
