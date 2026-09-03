from typing import Annotated

from careshield_contracts import AlgorithmResult
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_ai_realtime_service
from app.services.ai_realtime_service import AiRealtimeService
from app.core.config import load_ai_realtime_settings
from app.services.fraud_control_service import (
    FraudControlService,
    FraudControlUnavailableError,
)


router = APIRouter(prefix="/fraud-detection", tags=["fraud-detection"])


@router.get("/history", response_model=list[AlgorithmResult])
async def get_fraud_detection_history(
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AlgorithmResult]:
    """Return bounded, privacy-safe records of real fraud analyses."""
    return await service.fraud_history(limit)


@router.post("/alert/acknowledge")
async def acknowledge_fraud_alert() -> dict[str, bool]:
    service = FraudControlService(load_ai_realtime_settings())
    try:
        return await service.acknowledge_alert()
    except FraudControlUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
