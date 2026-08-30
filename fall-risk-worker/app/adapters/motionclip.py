from __future__ import annotations

from uuid import UUID

import httpx
from careshield_contracts import FallRiskModelResult


class MotionClipError(RuntimeError):
    """Safe error that never includes internal responses or credentials."""


class MotionClipClient:
    def __init__(self, base_url: str, shared_token: str, timeout_seconds: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.shared_token = shared_token
        self._client = httpx.AsyncClient(timeout=timeout_seconds, trust_env=False)
        self._ready = False

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.shared_token)

    @property
    def ready(self) -> bool:
        return self.configured and self._ready

    async def refresh_health(self) -> bool:
        if not self.configured:
            self._ready = False
            return False
        try:
            response = await self._client.get(f"{self.base_url}/health", timeout=5.0)
            payload = response.json() if response.status_code == 200 else {}
            self._ready = payload.get("ready") is True
        except (httpx.HTTPError, ValueError, TypeError):
            self._ready = False
        return self._ready

    async def predict(self, assessment_id: UUID) -> FallRiskModelResult:
        if not self.configured:
            raise MotionClipError("MotionCLIP worker is not configured")
        try:
            response = await self._client.post(
                f"{self.base_url}/internal/predict/gvhmr",
                headers={"Authorization": f"Bearer {self.shared_token}"},
                json={"assessment_id": str(assessment_id)},
            )
        except httpx.HTTPError as exc:
            raise MotionClipError("MotionCLIP worker is unavailable") from exc
        if response.status_code != 200:
            self._ready = False
            raise MotionClipError("MotionCLIP inference failed")
        try:
            result = FallRiskModelResult.model_validate(response.json())
            self._ready = True
            return result
        except (ValueError, TypeError) as exc:
            raise MotionClipError("MotionCLIP returned an invalid result") from exc

    async def close(self) -> None:
        await self._client.aclose()
