import asyncio

import httpx

from app.api.dependencies import get_device_service
from app.core.config import EzvizSettings
from app.main import app
from app.services.device_service import DeviceService


async def request(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


def test_missing_configuration_status_is_safe() -> None:
    secret = "must-never-appear"
    service = DeviceService(EzvizSettings("", secret))

    async def override_service() -> DeviceService:
        return service

    app.dependency_overrides[get_device_service] = override_service

    try:
        response = asyncio.run(request("/api/integrations/ezviz/status"))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "reachable": False,
        "message": "EZVIZ integration is not configured",
    }
    assert secret not in response.text
    assert "accessToken" not in response.text


def test_device_list_returns_503_when_not_configured() -> None:
    service = DeviceService(EzvizSettings("", ""))

    async def override_service() -> DeviceService:
        return service

    app.dependency_overrides[get_device_service] = override_service

    try:
        response = asyncio.run(request("/api/devices"))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "EZVIZ integration is not configured"}
