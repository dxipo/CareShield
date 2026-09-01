from typing import Annotated
from uuid import UUID

from careshield_contracts import (
    FallRiskAssessment,
    FallRiskAssessmentCreate,
    FallRiskVideoAssessmentCreate,
    FallRiskWorkerStatus,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.dependencies import get_fall_risk_service
from app.services.fall_risk_service import FallRiskService, FallRiskServiceError


router = APIRouter(prefix="/fall-risk", tags=["fall-risk"])
MAX_VIDEO_BYTES = 512 * 1024 * 1024


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


@router.post("/assessments/upload", response_model=FallRiskAssessment, status_code=202)
async def create_video_assessment(
    request: Request,
    service: Annotated[FallRiskService, Depends(get_fall_risk_service)],
    height_cm: Annotated[float, Query(ge=80.0, le=230.0)],
    capture_duration_seconds: Annotated[int, Query(ge=8, le=60)],
    source_filename: Annotated[str, Query(min_length=1, max_length=255)],
    subject_name: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    sex: Annotated[str | None, Query(pattern="^(male|female)$")] = None,
    age: Annotated[int | None, Query(ge=1, le=120)] = None,
) -> FallRiskAssessment:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "video/mp4":
        raise HTTPException(status_code=415, detail="Only MP4 video uploads are supported")
    raw_length = request.headers.get("content-length")
    content_length = int(raw_length) if raw_length and raw_length.isdigit() else None
    if content_length is not None and content_length > MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="Video upload exceeds the 512 MB limit")
    upload = FallRiskVideoAssessmentCreate(
        subject_name=subject_name,
        sex=sex,
        age=age,
        height_cm=height_cm,
        capture_duration_seconds=capture_duration_seconds,
        source_filename=source_filename,
    )
    try:
        return await service.create_from_video(upload, request.stream(), content_length)
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
