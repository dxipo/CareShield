import hashlib

from redis.asyncio import Redis

from careshield_contracts import AlgorithmResult, WorkerHeartbeat

from app.core.config import AiRealtimeSettings


class RealtimeStore:
    """Small Redis store for expiring worker state and latest results."""

    WORKER_PREFIX = "ai:worker:"
    LATEST_PREFIX = "ai:latest:"
    HISTORY_KEY = "ai:history:fall_detection"
    HISTORY_LIMIT = 100

    def __init__(self, settings: AiRealtimeSettings) -> None:
        self._settings = settings
        self._redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def save_worker(self, heartbeat: WorkerHeartbeat) -> None:
        await self._redis.set(
            f"{self.WORKER_PREFIX}{heartbeat.worker_id}",
            heartbeat.model_dump_json(),
            ex=self._settings.worker_ttl_seconds,
        )

    async def list_workers(self) -> list[WorkerHeartbeat]:
        workers: list[WorkerHeartbeat] = []
        async for key in self._redis.scan_iter(match=f"{self.WORKER_PREFIX}*"):
            payload = await self._redis.get(key)
            if payload:
                workers.append(WorkerHeartbeat.model_validate_json(payload))
        return sorted(workers, key=lambda worker: worker.worker_id)

    async def save_latest_result(self, result: AlgorithmResult) -> None:
        payload = result.model_dump_json()
        keys = {self._latest_key(result.task.value, result.device_id)}
        if result.device_id is not None:
            # A global alias lets the UI recover the latest result after reload;
            # the device-specific key remains available for future multi-camera use.
            keys.add(self._latest_key(result.task.value, None))
        for key in keys:
            await self._redis.set(
                key,
                payload,
                ex=self._settings.latest_result_ttl_seconds,
            )

    async def get_latest_result(
        self,
        task: str,
        device_id: str | None = None,
    ) -> AlgorithmResult | None:
        payload = await self._redis.get(self._latest_key(task, device_id))
        return AlgorithmResult.model_validate_json(payload) if payload else None

    async def append_fall_history(self, result: AlgorithmResult) -> None:
        """Keep meaningful, non-simulated state changes for operator review."""
        if result.simulated or result.task.value != "fall_detection":
            return
        previous_payload = await self._redis.lindex(self.HISTORY_KEY, 0)
        if previous_payload:
            previous = AlgorithmResult.model_validate_json(previous_payload)
            previous_alert = previous.metadata.get("alert_active")
            current_alert = result.metadata.get("alert_active")
            if previous.label == result.label and previous_alert == current_alert:
                return
        await self._redis.lpush(self.HISTORY_KEY, result.model_dump_json())
        await self._redis.ltrim(self.HISTORY_KEY, 0, self.HISTORY_LIMIT - 1)
        await self._redis.expire(
            self.HISTORY_KEY,
            self._settings.latest_result_ttl_seconds,
        )

    async def get_fall_history(self, limit: int = 20) -> list[AlgorithmResult]:
        payloads = await self._redis.lrange(
            self.HISTORY_KEY,
            0,
            min(max(limit, 1), self.HISTORY_LIMIT) - 1,
        )
        return [AlgorithmResult.model_validate_json(payload) for payload in payloads]

    async def close(self) -> None:
        await self._redis.aclose()

    @classmethod
    def _latest_key(cls, task: str, device_id: str | None) -> str:
        device_key = (
            hashlib.sha256(device_id.encode()).hexdigest()[:16]
            if device_id
            else "global"
        )
        return f"{cls.LATEST_PREFIX}{task}:{device_key}"
