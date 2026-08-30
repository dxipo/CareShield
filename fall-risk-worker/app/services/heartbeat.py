from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from careshield_contracts import AlgorithmCapabilities, WorkerHeartbeat

from app.core.config import FallRiskWorkerSettings
from app.services.assessment_service import FallRiskAssessmentService


class HeartbeatService:
    def __init__(
        self,
        settings: FallRiskWorkerSettings,
        assessment_service: FallRiskAssessmentService,
    ) -> None:
        self.settings = settings
        self.assessment_service = assessment_service
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(
            base_url=settings.backend_internal_url,
            headers={"Authorization": f"Bearer {settings.shared_token}"},
            timeout=10.0,
            trust_env=False,
        )

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="fall-risk-heartbeat")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._client.aclose()

    async def _loop(self) -> None:
        while True:
            await self.assessment_service.refresh_motionclip()
            worker_status = self.assessment_service.status()
            heartbeat = WorkerHeartbeat(
                worker_id=self.settings.worker_id,
                online=True,
                timestamp=datetime.now(timezone.utc),
                version=self.settings.worker_version,
                capabilities=AlgorithmCapabilities(
                    fall_risk="installed" if worker_status.ready else "unavailable"
                ),
                runtime={"fall_risk": worker_status.model_dump(mode="json")},
            )
            try:
                response = await self._client.post(
                    "/internal/ai/heartbeat",
                    json=heartbeat.model_dump(mode="json"),
                )
                response.raise_for_status()
            except httpx.HTTPError:
                pass
            await asyncio.sleep(self.settings.heartbeat_interval_seconds)
