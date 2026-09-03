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
        await self._store.append_fraud_history(result)
        await self._store.append_fraud_event(result)
        envelope = self._envelope(
            RealtimeMessageType.ALGORITHM_RESULT,
            result.model_dump(mode="json"),
        )
        await self._hub.broadcast(envelope)
        return envelope

    async def fall_history(self, limit: int = 20) -> list[AlgorithmResult]:
        return await self._store.get_fall_history(limit)

    async def fraud_history(self, limit: int = 20) -> list[AlgorithmResult]:
        return await self._store.get_fraud_history(limit)

    async def risk_events(self, limit: int = 50) -> list[AlgorithmResult]:
        return await self._store.get_risk_events(limit)

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
            latest_fraud_detection = await self._store.get_latest_result(
                AlgorithmTask.FRAUD_DETECTION.value
            )
        except Exception:
            return {
                "redis_reachable": False,
                "workers": [],
                "capabilities": AlgorithmCapabilities(),
                "latest_pipeline_test": None,
                "latest_fall_detection": None,
                "latest_fraud_detection": None,
            }

        capabilities = self._aggregate_capabilities(workers)
        return {
            "redis_reachable": redis_reachable,
            "workers": workers,
            "capabilities": capabilities,
            "latest_pipeline_test": latest,
            "latest_fall_detection": latest_fall_detection,
            "latest_fraud_detection": latest_fraud_detection,
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
    def _aggregate_capabilities(workers: list[WorkerHeartbeat]) -> AlgorithmCapabilities:
        priority = {
            "not_installed": 0,
            "unavailable": 1,
            "error": 2,
            "installed": 3,
            "starting": 4,
            "running": 5,
        }

        def best(name: str):
            values = [getattr(worker.capabilities, name) for worker in workers]
            return max(values, key=lambda value: priority[value], default="not_installed")

        return AlgorithmCapabilities(
            fall_detection=best("fall_detection"),
            fall_risk=best("fall_risk"),
            fraud_detection=best("fraud_detection"),
        )

    @staticmethod
    def _envelope(message_type: RealtimeMessageType, data: dict) -> RealtimeEnvelope:
        return RealtimeEnvelope(
            type=message_type,
            timestamp=datetime.now(timezone.utc),
            data=data,
        )
