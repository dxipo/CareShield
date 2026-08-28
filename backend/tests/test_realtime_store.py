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
        self.lists: dict[str, list[str]] = {}

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

    async def lindex(self, key, index):
        values = self.lists.get(key, [])
        return values[index] if len(values) > index else None

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    async def expire(self, key, seconds):
        self.expirations[key] = seconds

    async def lrange(self, key, start, end):
        return self.lists.get(key, [])[start:end + 1]

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


def test_device_result_is_saved_under_device_and_global_latest_keys() -> None:
    async def run() -> None:
        store = RealtimeStore(settings())
        fake = FakeRedis()
        store._redis = fake
        result = AlgorithmResult(
            result_id=uuid4(),
            task=AlgorithmTask.FALL_DETECTION,
            model_id="pose-fall-baseline",
            model_version="m5-v1",
            device_id="ezviz_safe_id",
            result_timestamp=datetime.now(timezone.utc),
            label="normal",
            score=0.1,
            simulated=False,
        )

        await store.save_latest_result(result)

        fall_keys = [key for key in fake.values if key.startswith("ai:latest:fall_detection")]
        assert len(fall_keys) == 2
        restored = await store.get_latest_result("fall_detection")
        assert restored is not None and restored.result_id == result.result_id

    asyncio.run(run())


def test_fall_history_keeps_real_state_changes_without_duplicate_heartbeats() -> None:
    async def run() -> None:
        store = RealtimeStore(settings())
        fake = FakeRedis()
        store._redis = fake

        def result(label: str) -> AlgorithmResult:
            return AlgorithmResult(
                result_id=uuid4(),
                task=AlgorithmTask.FALL_DETECTION,
                model_id="stgcn-extend",
                model_version="m5.2",
                result_timestamp=datetime.now(timezone.utc),
                label=label,
                metadata={"alert_active": label == "fallen"},
                simulated=False,
            )

        await store.append_fall_history(result("normal"))
        await store.append_fall_history(result("normal"))
        await store.append_fall_history(result("fallen"))

        history = await store.get_fall_history()
        assert [item.label for item in history] == ["fallen", "normal"]
        assert fake.expirations[store.HISTORY_KEY] == 1234

    asyncio.run(run())
