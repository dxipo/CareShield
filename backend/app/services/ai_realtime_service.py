from datetime import datetime, timezone

from careshield_contracts import (
    AlgorithmCapabilities,
    AlgorithmResult,
    AlgorithmTask,
    RealtimeEnvelope,
    RealtimeMessageType,
    WorkerHeartbeat,
)

from app.services.realtime_hub import RealtimeHub
from app.services.realtime_store import RealtimeStore


class AiRealtimeService:
    def __init__(self, store: RealtimeStore, hub: RealtimeHub) -> None:
        self._store = store
        self._hub = hub

    async def ingest_result(self, result: AlgorithmResult) -> RealtimeEnvelope:
        await self._store.save_latest_result(result)
        await self._store.append_fall_history(result)
        envelope = self._envelope(
            RealtimeMessageType.ALGORITHM_RESULT,
            result.model_dump(mode="json"),
        )
        await self._hub.broadcast(envelope)
        return envelope

    async def fall_history(self, limit: int = 20) -> list[AlgorithmResult]:
        return await self._store.get_fall_history(limit)

    async def record_heartbeat(self, heartbeat: WorkerHeartbeat) -> RealtimeEnvelope:
        await self._store.save_worker(heartbeat)
        envelope = self._envelope(
            RealtimeMessageType.WORKER_STATUS,
            heartbeat.model_dump(mode="json"),
        )
        await self._hub.broadcast(envelope)
        return envelope

    async def status_snapshot(self) -> dict:
        try:
            redis_reachable = await self._store.ping()
            workers = await self._store.list_workers()
            latest = await self._store.get_latest_result(
                AlgorithmTask.PIPELINE_TEST.value
            )
            latest_fall_detection = await self._store.get_latest_result(
                AlgorithmTask.FALL_DETECTION.value
            )
        except Exception:
            return {
                "redis_reachable": False,
                "workers": [],
                "capabilities": AlgorithmCapabilities(),
                "latest_pipeline_test": None,
                "latest_fall_detection": None,
            }

        capabilities = workers[0].capabilities if workers else AlgorithmCapabilities()
        return {
            "redis_reachable": redis_reachable,
            "workers": workers,
            "capabilities": capabilities,
            "latest_pipeline_test": latest,
            "latest_fall_detection": latest_fall_detection,
        }

    async def initial_messages(self) -> list[RealtimeEnvelope]:
        snapshot = await self.status_snapshot()
        return [
            self._envelope(
                RealtimeMessageType.WORKER_STATUS,
                worker.model_dump(mode="json"),
            )
            for worker in snapshot["workers"]
        ]

    async def close(self) -> None:
        await self._store.close()

    @staticmethod
    def _envelope(message_type: RealtimeMessageType, data: dict) -> RealtimeEnvelope:
        return RealtimeEnvelope(
            type=message_type,
            timestamp=datetime.now(timezone.utc),
            data=data,
        )
