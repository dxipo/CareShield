from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from careshield_contracts import AlgorithmCapabilities, WorkerHeartbeat

from app.core.config import FraudWorkerSettings
from app.publisher.result_publisher import PublishError, ResultPublisher
from app.services.fraud_detection_service import FraudDetectionService


logger = logging.getLogger(__name__)


class WorkerRuntime:
    def __init__(
        self,
        settings: FraudWorkerSettings,
        publisher: ResultPublisher,
        service: FraudDetectionService,
    ) -> None:
        self.settings = settings
        self.publisher = publisher
        self.service = service
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self.service.start()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="fraud-heartbeat"
        )

    async def stop(self) -> None:
        await self.service.stop()
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.publisher.close()

    def heartbeat_payload(self) -> WorkerHeartbeat:
        return WorkerHeartbeat(
            worker_id=self.settings.worker_id,
            online=True,
            timestamp=datetime.now(timezone.utc),
            version=self.settings.worker_version,
            capabilities=AlgorithmCapabilities(
                fraud_detection=self.service.capability,
            ),
            runtime=self.service.runtime_metadata(),
        )

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self.publisher.heartbeat(self.heartbeat_payload())
            except PublishError:
                logger.warning("Fraud Worker heartbeat delivery failed")
            await asyncio.sleep(self.settings.heartbeat_interval_seconds)
