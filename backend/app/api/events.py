from typing import Annotated

from careshield_contracts import AlgorithmResult
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_ai_realtime_service
from app.services.ai_realtime_service import AiRealtimeService


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[AlgorithmResult])
async def get_risk_events(
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AlgorithmResult]:
    """Return persisted real risk events; diagnostic state changes are excluded."""
    return await service.risk_events(limit)
