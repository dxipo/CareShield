import asyncio

import httpx

from app.core.config import AiRealtimeSettings
from app.services.fraud_control_service import FraudControlService


def test_fraud_alert_acknowledgement_uses_internal_auth() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/internal/fraud-detection/alert/acknowledge"
            assert request.headers["Authorization"] == "Bearer test-token"
            return httpx.Response(
                200,
                json={"alert_active": False, "alert_acknowledged": True},
            )

        settings = AiRealtimeSettings(
            app_env="test",
            redis_url="redis://unused/0",
            shared_token="test-token",
            worker_ttl_seconds=30,
            latest_result_ttl_seconds=60,
            fraud_worker_internal_url="http://fraud.test",
        )
        result = await FraudControlService(
            settings,
            transport=httpx.MockTransport(handler),
        ).acknowledge_alert()
        assert result == {"alert_active": False, "alert_acknowledged": True}

    asyncio.run(run())
