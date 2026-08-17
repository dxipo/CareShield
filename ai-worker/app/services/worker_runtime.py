import asyncio
import logging
from datetime import datetime, timezone

from careshield_contracts import AlgorithmCapabilities, WorkerHeartbeat

from app.core.config import WorkerSettings
from app.publisher.result_publisher import PublishError, ResultPublisher
from app.services.fall_detection_service import FallDetectionService

logger = logging.getLogger(__name__)


class WorkerRuntime:
    def __init__(
        self,
        settings: WorkerSettings,
        publisher: ResultPublisher,
        fall_service: FallDetectionService | None = None,
    ) -> None:
        self.settings = settings
        self.publisher = publisher
        self.fall_service = fall_service
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def capabilities(self) -> AlgorithmCapabilities:
        return AlgorithmCapabilities(
            fall_detection=(
                self.fall_service.capability
                if self.fall_service is not None
                else "not_installed"
            ),
        )

    async def start(self) -> None:
        if self.fall_service is not None:
            await self.fall_service.start()
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self.fall_service is not None:
            await self.fall_service.stop()
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
            runtime=(
                self.fall_service.runtime_metadata()
                if self.fall_service is not None
                else {}
            ),
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
