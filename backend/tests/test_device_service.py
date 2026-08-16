import asyncio
from typing import Any

import pytest

from app.adapters.ezviz.exceptions import EzvizNotConfiguredError
from app.core.config import EzvizSettings
from app.services.device_service import DeviceService


class FakeEzvizClient:
    async def list_all_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "deviceSerial": "TEST123456",
                "deviceName": "Living room camera",
                "deviceType": "CS-H6c",
                "status": 1,
                "parentCategory": "IPC",
                "cameraNum": 1,
                "updateTime": 1_700_000_000_000,
                "cameraInfo": [{"cameraNo": 1, "cameraName": "Camera 1"}],
            }
        ]

    async def get_device_info(self, device_serial: str) -> dict[str, Any]:
        return {
            "deviceSerial": device_serial,
            "deviceName": "Living room camera",
            "localName": "H6c",
            "model": "CS-H6c-8WFL",
            "status": 0,
            "parentCategory": "IPC",
            "updateTime": 1_700_000_100_000,
            "netType": "wireless",
            "signal": "80%",
        }

    async def check_reachable(self) -> None:
        return None

    async def close(self) -> None:
        return None


def test_device_list_response_mapping() -> None:
    service = DeviceService(
        EzvizSettings("example-key", "example-secret"),
        FakeEzvizClient(),  # type: ignore[arg-type]
    )

    devices = asyncio.run(service.list_devices())

    assert len(devices) == 1
    device = devices[0]
    assert device.provider == "ezviz"
    assert device.device_serial == "TEST123456"
    assert device.model == "CS-H6c"
    assert device.online is True
    assert device.status == "online"
    assert device.device_type == "IPC"
    assert device.camera_count == 1
    assert device.channels[0].number == 1
    assert device.updated_at is not None
    assert device.id.startswith("ezviz_")
    assert "TEST123456" not in device.id


def test_device_detail_response_mapping() -> None:
    service = DeviceService(
        EzvizSettings("example-key", "example-secret"),
        FakeEzvizClient(),  # type: ignore[arg-type]
    )

    device = asyncio.run(service.get_device("TEST123456"))

    assert device.device_serial == "TEST123456"
    assert device.model == "CS-H6c-8WFL"
    assert device.online is False
    assert device.status == "offline"
    assert device.local_name == "H6c"
    assert device.network_type == "wireless"
    assert device.signal == "80%"


def test_missing_ezviz_configuration_does_not_build_client() -> None:
    service = DeviceService(EzvizSettings("", ""))

    status = asyncio.run(service.integration_status())
    assert status.configured is False
    assert status.reachable is False

    with pytest.raises(EzvizNotConfiguredError):
        asyncio.run(service.list_devices())
