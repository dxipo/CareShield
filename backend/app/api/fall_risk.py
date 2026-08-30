from typing import Annotated
from uuid import UUID

from careshield_contracts import (
    FallRiskAssessment,
    FallRiskAssessmentCreate,
    FallRiskWorkerStatus,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.dependencies import get_fall_risk_service
from app.services.fall_risk_service import FallRiskService, FallRiskServiceError


router = APIRouter(prefix="/fall-risk", tags=["fall-risk"])


@router.get("/status", response_model=FallRiskWorkerStatus)
async def get_status(
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
) -> FallRiskWorkerStatus:
    try:
        return await service.status()
    except FallRiskServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/assessments", response_model=FallRiskAssessment, status_code=202)
async def create_assessment(
    request: FallRiskAssessmentCreate,
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
) -> FallRiskAssessment:
    try:
        return await service.create(request)
    except FallRiskServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/assessments", response_model=list[FallRiskAssessment])
async def list_assessments(
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[FallRiskAssessment]:
    try:
        return await service.list(limit)
    except FallRiskServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/assessments/{assessment_id}", response_model=FallRiskAssessment)
async def get_assessment(
    assessment_id: UUID,
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
) -> FallRiskAssessment:
    try:
        return await service.get(assessment_id)
    except FallRiskServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/assessments/{assessment_id}/risk-model", response_model=FallRiskAssessment)
async def run_risk_model(
    assessment_id: UUID,
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
) -> FallRiskAssessment:
    try:
        return await service.run_risk_model(assessment_id)
    except FallRiskServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/assessments/{assessment_id}/artifacts/{artifact_id}")
async def get_assessment_artifact(
    assessment_id: UUID,
    artifact_id: str,
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
) -> StreamingResponse:
    try:
        response = await service.open_artifact(assessment_id, artifact_id)
    except FallRiskServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    headers = {"Cache-Control": "private, no-store"}
    content_length = response.headers.get("content-length")
    if content_length:
        headers["Content-Length"] = content_length
    return StreamingResponse(
        response.aiter_bytes(),
        media_type=response.headers.get("content-type", "video/mp4"),
        headers=headers,
        background=BackgroundTask(response.aclose),
    )
