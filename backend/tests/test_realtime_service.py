import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from careshield_contracts import (
    AlgorithmCapabilities,
    AlgorithmResult,
    AlgorithmTask,
    RealtimeMessageType,
    WorkerHeartbeat,
)

from app.services.ai_realtime_service import AiRealtimeService
from app.services.realtime_hub import RealtimeHub


class RecordingStore:
    def __init__(self) -> None:
        self.latest = None

    async def save_latest_result(self, result):
        self.latest = result

    async def append_fall_history(self, result):
        return None

    async def append_fraud_history(self, result):
        return None

    async def append_fraud_event(self, result):
        return None


class RecordingSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.payloads = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.payloads.append(payload)


def test_ingest_serializes_and_broadcasts_unified_websocket_envelope() -> None:
    async def run() -> None:
        store = RecordingStore()
        hub = RealtimeHub()
        socket = RecordingSocket()
        await hub.connect(socket)
        result = AlgorithmResult(
            result_id=uuid4(),
            task=AlgorithmTask.PIPELINE_TEST,
            model_id="pipeline-tester",
            model_version="1.0",
            result_timestamp=datetime.now(timezone.utc),
            label="pipeline_ok",
            simulated=True,
        )

        envelope = await AiRealtimeService(store, hub).ingest_result(result)

        assert store.latest is result
        assert envelope.type == RealtimeMessageType.ALGORITHM_RESULT
        assert socket.payloads[0]["type"] == "algorithm_result"
        assert socket.payloads[0]["data"]["simulated"] is True
        assert "playback_url" not in str(socket.payloads[0])

    asyncio.run(run())


def test_websocket_initial_state_does_not_replay_stale_result_as_live() -> None:
    class SnapshotStore:
        async def ping(self):
            return True

        async def list_workers(self):
            return [
                WorkerHeartbeat(
                    worker_id="worker-1",
                    online=True,
                    timestamp=datetime.now(timezone.utc),
                    version="0.4.0",
                    capabilities=AlgorithmCapabilities(),
                )
            ]

        async def get_latest_result(self, task):
            return AlgorithmResult(
                result_id=uuid4(),
                task=AlgorithmTask.PIPELINE_TEST,
                model_id="pipeline-tester",
                model_version="1.0",
                result_timestamp=datetime.now(timezone.utc),
                label="pipeline_ok",
                simulated=True,
            )

    async def run() -> None:
        messages = await AiRealtimeService(SnapshotStore(), RealtimeHub()).initial_messages()
        assert [message.type for message in messages] == [
            RealtimeMessageType.WORKER_STATUS
        ]

    asyncio.run(run())


def test_capabilities_are_aggregated_across_isolated_workers() -> None:
    workers = [
        WorkerHeartbeat(
            worker_id="realtime-worker",
            online=True,
            timestamp=datetime.now(timezone.utc),
            version="0.5.0",
            capabilities=AlgorithmCapabilities(fall_detection="running"),
        ),
        WorkerHeartbeat(
            worker_id="risk-worker",
            online=True,
            timestamp=datetime.now(timezone.utc),
            version="0.6.0",
            capabilities=AlgorithmCapabilities(fall_risk="installed"),
        ),
        WorkerHeartbeat(
            worker_id="fraud-worker",
            online=True,
            timestamp=datetime.now(timezone.utc),
            version="0.7.0",
            capabilities=AlgorithmCapabilities(fraud_detection="running"),
        ),
    ]
    result = AiRealtimeService._aggregate_capabilities(workers)
    assert result.fall_detection == "running"
    assert result.fall_risk == "installed"
    assert result.fraud_detection == "running"
