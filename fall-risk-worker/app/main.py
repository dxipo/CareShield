from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from careshield_contracts import (
    FallRiskAssessment,
    FallRiskAssessmentCreate,
    FallRiskWorkerStatus,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.config import load_settings
from app.services.assessment_service import (
    AssessmentArtifactNotFoundError,
    AssessmentBusyError,
    FallRiskAssessmentService,
    RiskModelInputError,
    WorkerNotReadyError,
)
from app.services.job_store import AssessmentNotFoundError
from app.services.heartbeat import HeartbeatService


settings = load_settings()
service = FallRiskAssessmentService(settings)
heartbeat_service = HeartbeatService(settings, service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await heartbeat_service.start()
    yield
    await heartbeat_service.stop()
    await service.close()


app = FastAPI(title="CareShield Fall Risk Worker", version="0.6.1", lifespan=lifespan)


def require_internal_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    if not (
        settings.shared_token
        and scheme.lower() == "bearer"
        and secrets.compare_digest(token, settings.shared_token)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "fall-risk-worker"}


@app.get("/status", response_model=FallRiskWorkerStatus)
async def worker_status() -> FallRiskWorkerStatus:
    await service.refresh_motionclip()
    return service.status()


@app.post(
    "/internal/assessments",
    response_model=FallRiskAssessment,
    dependencies=[Depends(require_internal_token)],
)
async def create_assessment(request: FallRiskAssessmentCreate) -> FallRiskAssessment:
    try:
        return await service.create(request)
    except WorkerNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AssessmentBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/internal/assessments",
    response_model=list[FallRiskAssessment],
    dependencies=[Depends(require_internal_token)],
)
async def list_assessments(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[FallRiskAssessment]:
    return await service.store.list(limit)


@app.get(
    "/internal/assessments/{assessment_id}",
    response_model=FallRiskAssessment,
    dependencies=[Depends(require_internal_token)],
)
async def get_assessment(assessment_id: UUID) -> FallRiskAssessment:
    try:
        return await service.store.get(assessment_id)
    except AssessmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc


@app.post(
    "/internal/assessments/{assessment_id}/risk-model",
    response_model=FallRiskAssessment,
    dependencies=[Depends(require_internal_token)],
)
async def run_risk_model(assessment_id: UUID) -> FallRiskAssessment:
    try:
        return await service.run_risk_model(assessment_id)
    except AssessmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc
    except AssessmentBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RiskModelInputError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkerNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/internal/assessments/{assessment_id}/artifacts/{artifact_id}",
    dependencies=[Depends(require_internal_token)],
    response_class=FileResponse,
)
async def get_assessment_artifact(assessment_id: UUID, artifact_id: str) -> FileResponse:
    try:
        path = await service.artifact_path(assessment_id, artifact_id)
    except (AssessmentNotFoundError, AssessmentArtifactNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Assessment artifact not found") from exc
    return FileResponse(path, media_type="video/mp4", filename=f"{artifact_id}.mp4")
