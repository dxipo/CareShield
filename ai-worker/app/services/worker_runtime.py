import asyncio
import logging
from datetime import datetime, timezone

from careshield_contracts import AlgorithmCapabilities, WorkerHeartbeat

from app.core.config import WorkerSettings
from app.publisher.result_publisher import PublishError, ResultPublisher

logger = logging.getLogger(__name__)


class WorkerRuntime:
    def __init__(self, settings: WorkerSettings, publisher: ResultPublisher) -> None:
        self.settings = settings
        self.publisher = publisher
        self.capabilities = AlgorithmCapabilities()
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        await self.publisher.close()

    def heartbeat_payload(self) -> WorkerHeartbeat:
        return WorkerHeartbeat(
            worker_id=self.settings.worker_id,
            online=True,
            timestamp=datetime.now(timezone.utc),
            version=self.settings.worker_version,
            capabilities=self.capabilities,
        )

    async def send_heartbeat(self) -> None:
        await self.publisher.heartbeat(self.heartbeat_payload())

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self.send_heartbeat()
            except PublishError:
                logger.warning("AI Worker heartbeat delivery failed")
            await asyncio.sleep(self.settings.heartbeat_interval_seconds)
