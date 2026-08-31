from __future__ import annotations

import httpx

from careshield_contracts import AlgorithmResult, WorkerHeartbeat

from app.core.config import FraudWorkerSettings


class PublishError(RuntimeError):
    """Safe publishing failure without response bodies or credentials."""


class ResultPublisher:
    def __init__(
        self,
        settings: FraudWorkerSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.backend_internal_url,
            headers={"Authorization": f"Bearer {settings.shared_token}"},
            timeout=settings.request_timeout_seconds,
            transport=transport,
            trust_env=False,
        )

    async def publish(self, result: AlgorithmResult) -> None:
        await self._post("/internal/ai/results", result.model_dump(mode="json"))

    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        await self._post("/internal/ai/heartbeat", heartbeat.model_dump(mode="json"))

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict) -> None:
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PublishError(
                f"Backend rejected Fraud Worker request with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PublishError("Backend AI ingest is unreachable") from exc
