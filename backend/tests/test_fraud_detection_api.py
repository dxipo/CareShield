import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from careshield_contracts import AlgorithmResult, AlgorithmTask

from app.api.dependencies import get_ai_realtime_service
from app.main import app


class RecordingService:
    async def fraud_history(self, limit: int):
        assert limit == 5
        return [
            AlgorithmResult(
                result_id=uuid4(),
                task=AlgorithmTask.FRAUD_DETECTION,
                model_id="fraud-ensemble",
                model_version="m7-v1",
                result_timestamp=datetime.now(timezone.utc),
                label="normal",
                score=0.0,
                level="normal",
                metadata={"transcript_preview": "测试文本"},
                simulated=False,
            )
        ]


def test_fraud_detection_history_endpoint() -> None:
    async def request_history() -> httpx.Response:
        async def override_service():
            return RecordingService()

        app.dependency_overrides[get_ai_realtime_service] = override_service
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.get("/api/fraud-detection/history?limit=5")
        finally:
            app.dependency_overrides.clear()

    response = asyncio.run(request_history())

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["task"] == "fraud_detection"
    assert payload[0]["simulated"] is False
