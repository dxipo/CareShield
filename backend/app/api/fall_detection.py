from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from careshield_contracts import AlgorithmResult

from app.api.dependencies import get_ai_realtime_service
from app.core.config import load_ai_realtime_settings
from app.services.ai_realtime_service import AiRealtimeService
from app.services.fall_preview_service import FallPreviewService
from app.services.fall_preview_service import FallPreviewUnavailableError


router = APIRouter(prefix="/fall-detection", tags=["fall-detection"])


@router.get("/preview.mjpeg", response_class=StreamingResponse)
async def get_fall_detection_preview() -> StreamingResponse:
    service = FallPreviewService(load_ai_realtime_settings())
    return StreamingResponse(
        service.stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/history", response_model=list[AlgorithmResult])
async def get_fall_detection_history(
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AlgorithmResult]:
    return await service.fall_history(limit)


@router.post("/alert/acknowledge")
async def acknowledge_fall_alert() -> dict[str, bool]:
    service = FallPreviewService(load_ai_realtime_settings())
    try:
        return await service.acknowledge_alert()
    except FallPreviewUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
