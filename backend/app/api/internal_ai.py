import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from careshield_contracts import AlgorithmResult, WorkerHeartbeat

from app.api.dependencies import get_ai_realtime_service
from app.core.config import load_ai_realtime_settings
from app.schemas.algorithm import HeartbeatAcceptedResponse, IngestAcceptedResponse
from app.services.ai_realtime_service import AiRealtimeService

router = APIRouter(prefix="/internal/ai", tags=["internal-ai"])


async def verify_worker_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = load_ai_realtime_settings()
    if not settings.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Worker integration is not configured",
        )
    scheme, _, token = (authorization or "").partition(" ")
    valid = scheme.lower() == "bearer" and secrets.compare_digest(
        token,
        settings.shared_token,
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal worker credentials",
        )


@router.post(
    "/results",
    response_model=IngestAcceptedResponse,
    dependencies=[Depends(verify_worker_token)],
)
async def ingest_result(
    result: AlgorithmResult,
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
) -> IngestAcceptedResponse:
    await service.ingest_result(result)
    return IngestAcceptedResponse(status="accepted", result_id=str(result.result_id))


@router.post(
    "/heartbeat",
    response_model=HeartbeatAcceptedResponse,
    dependencies=[Depends(verify_worker_token)],
)
async def ingest_heartbeat(
    heartbeat: WorkerHeartbeat,
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
) -> HeartbeatAcceptedResponse:
    await service.record_heartbeat(heartbeat)
    return HeartbeatAcceptedResponse(status="accepted", worker_id=heartbeat.worker_id)
