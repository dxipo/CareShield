from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_ai_realtime_service
from app.schemas.algorithm import SystemStatusResponse
from app.services.ai_realtime_service import AiRealtimeService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
) -> SystemStatusResponse:
    snapshot = await service.status_snapshot()
    return SystemStatusResponse(
        backend="online",
        redis="healthy" if snapshot["redis_reachable"] else "unavailable",
        ai_worker="online" if snapshot["workers"] else "offline",
    )
