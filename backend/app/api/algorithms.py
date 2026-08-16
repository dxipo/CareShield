from typing import Annotated

from fastapi import APIRouter, Depends
from careshield_contracts import WorkerHeartbeat

from app.api.dependencies import get_ai_realtime_service
from app.schemas.algorithm import AlgorithmsStatusResponse
from app.services.ai_realtime_service import AiRealtimeService

router = APIRouter(prefix="/algorithms", tags=["algorithms"])


@router.get("", response_model=AlgorithmsStatusResponse)
async def get_algorithms_status(
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
) -> AlgorithmsStatusResponse:
    return AlgorithmsStatusResponse.model_validate(await service.status_snapshot())


@router.get("/workers", response_model=list[WorkerHeartbeat])
async def get_workers(
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
) -> list[WorkerHeartbeat]:
    snapshot = await service.status_snapshot()
    return snapshot["workers"]
