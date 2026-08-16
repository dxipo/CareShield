import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from careshield_contracts import (
    AlgorithmCapabilities,
    AlgorithmResult,
    AlgorithmTask,
    WorkerHeartbeat,
)

from app.core.config import AiRealtimeSettings
from app.services.realtime_store import RealtimeStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def ping(self):
        return True

    async def set(self, key, value, ex):
        self.values[key] = value
        self.expirations[key] = ex

    async def get(self, key):
        return self.values.get(key)

    async def scan_iter(self, match):
        prefix = match.removesuffix("*")
        for key in self.values:
            if key.startswith(prefix):
                yield key

    async def aclose(self):
        return None


def settings() -> AiRealtimeSettings:
    return AiRealtimeSettings(
        app_env="development",
        redis_url="redis://unused/0",
        shared_token="test",
        worker_ttl_seconds=27,
        latest_result_ttl_seconds=1234,
    )


def test_redis_store_uses_worker_ttl_and_latest_result_ttl() -> None:
    async def run() -> None:
        store = RealtimeStore(settings())
        fake = FakeRedis()
        store._redis = fake
        heartbeat = WorkerHeartbeat(
            worker_id="worker-1",
            online=True,
            timestamp=datetime.now(timezone.utc),
            version="0.4.0",
            capabilities=AlgorithmCapabilities(),
        )
        result = AlgorithmResult(
            result_id=uuid4(),
            task=AlgorithmTask.PIPELINE_TEST,
            model_id="pipeline-tester",
            model_version="1.0",
            result_timestamp=datetime.now(timezone.utc),
            label="pipeline_ok",
            simulated=True,
        )

        await store.save_worker(heartbeat)
        await store.save_latest_result(result)

        assert fake.expirations["ai:worker:worker-1"] == 27
        latest_key = next(key for key in fake.values if key.startswith("ai:latest:"))
        assert fake.expirations[latest_key] == 1234
        assert (await store.list_workers())[0].worker_id == "worker-1"
        restored = await store.get_latest_result("pipeline_test")
        assert restored is not None and restored.result_id == result.result_id

    asyncio.run(run())
