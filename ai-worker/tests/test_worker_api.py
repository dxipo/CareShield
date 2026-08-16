import asyncio

import httpx

from app.main import app


def get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(request())


def test_health() -> None:
    response = get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ai-worker"}


def test_capabilities_truthfully_report_no_models() -> None:
    response = get("/capabilities")
    assert response.status_code == 200
    assert response.json() == {
        "fall_detection": "not_installed",
        "fall_risk": "not_installed",
        "fraud_detection": "not_installed",
    }
