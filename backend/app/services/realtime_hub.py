from fastapi import WebSocket

from careshield_contracts import RealtimeEnvelope


class RealtimeHub:
    """In-process browser connection registry for the single realtime channel."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def send(self, websocket: WebSocket, envelope: RealtimeEnvelope) -> None:
        await websocket.send_json(envelope.model_dump(mode="json"))

    async def broadcast(self, envelope: RealtimeEnvelope) -> None:
        stale: list[WebSocket] = []
        payload = envelope.model_dump(mode="json")
        for websocket in tuple(self._connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)
