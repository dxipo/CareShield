from __future__ import annotations

from collections.abc import AsyncIterable
from uuid import UUID

import httpx
from careshield_contracts import (
    FallRiskAssessment,
    FallRiskAssessmentCreate,
    FallRiskVideoAssessmentCreate,
    FallRiskWorkerStatus,
)

from app.core.config import AiRealtimeSettings


class FallRiskServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class FallRiskService:
    """Backend boundary for the isolated fall-risk batch worker."""

    def __init__(
        self,
        settings: AiRealtimeSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.fall_risk_worker_internal_url,
            headers={"Authorization": f"Bearer {settings.shared_token}"},
            timeout=15.0,
            transport=transport,
            trust_env=False,
        )

    async def status(self) -> FallRiskWorkerStatus:
        response = await self._request("GET", "/status")
        return FallRiskWorkerStatus.model_validate(response.json())

    async def create(self, request: FallRiskAssessmentCreate) -> FallRiskAssessment:
        response = await self._request(
            "POST",
            "/internal/assessments",
            json=request.model_dump(mode="json"),
        )
        return FallRiskAssessment.model_validate(response.json())

    async def create_from_video(
        self,
        request: FallRiskVideoAssessmentCreate,
        content: AsyncIterable[bytes],
        content_length: int | None,
    ) -> FallRiskAssessment:
        headers = {"Content-Type": "video/mp4"}
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        response = await self._request(
            "POST",
            "/internal/assessments/upload",
            params={
                "height_cm": request.height_cm,
                "capture_duration_seconds": request.capture_duration_seconds,
                "source_filename": request.source_filename,
            },
            headers=headers,
            content=content,
            timeout=120.0,
        )
        return FallRiskAssessment.model_validate(response.json())

    async def list(self, limit: int = 20) -> list[FallRiskAssessment]:
        response = await self._request(
            "GET", "/internal/assessments", params={"limit": limit}
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise FallRiskServiceError("Fall-risk worker response is invalid")
        return [FallRiskAssessment.model_validate(item) for item in payload]

    async def get(self, assessment_id: UUID) -> FallRiskAssessment:
        response = await self._request(
            "GET", f"/internal/assessments/{assessment_id}"
        )
        return FallRiskAssessment.model_validate(response.json())

    async def run_risk_model(self, assessment_id: UUID) -> FallRiskAssessment:
        response = await self._request(
            "POST", f"/internal/assessments/{assessment_id}/risk-model"
        )
        return FallRiskAssessment.model_validate(response.json())

    async def open_artifact(self, assessment_id: UUID, artifact_id: str) -> httpx.Response:
        request = self._client.build_request(
            "GET", f"/internal/assessments/{assessment_id}/artifacts/{artifact_id}"
        )
        try:
            response = await self._client.send(request, stream=True)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            await exc.response.aclose()
            if exc.response.status_code == 404:
                raise FallRiskServiceError("Fall-risk artifact was not found", 404) from exc
            raise FallRiskServiceError("Fall-risk artifact request failed", 502) from exc
        except httpx.HTTPError as exc:
            raise FallRiskServiceError("Fall-risk worker is unavailable", 503) from exc

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            safe_status = exc.response.status_code
            if safe_status in {401, 403}:
                message = "Fall-risk worker authentication failed"
                safe_status = 503
            elif safe_status == 409:
                message = "A fall-risk assessment is already running"
            elif safe_status in {400, 413, 415, 422}:
                message = "The uploaded assessment video is invalid"
                safe_status = 400
            elif safe_status == 404:
                message = "Fall-risk assessment was not found"
            elif safe_status == 503:
                message = "Fall-risk worker is not ready"
            else:
                message = "Fall-risk worker request failed"
                safe_status = 502
            raise FallRiskServiceError(message, safe_status) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise FallRiskServiceError("Fall-risk worker is unavailable", 503) from exc
