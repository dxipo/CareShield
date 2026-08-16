from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_ai_realtime_service, get_realtime_hub
from app.services.ai_realtime_service import AiRealtimeService
from app.services.realtime_hub import RealtimeHub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/realtime")
async def realtime_channel(
    websocket: WebSocket,
    hub: Annotated[RealtimeHub, Depends(get_realtime_hub)],
    service: Annotated[AiRealtimeService, Depends(get_ai_realtime_service)],
) -> None:
    await hub.connect(websocket)
    try:
        for envelope in await service.initial_messages():
            await hub.send(websocket, envelope)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)
    except Exception:
        hub.disconnect(websocket)
        await websocket.close()
