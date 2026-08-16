from app.core.config import load_ezviz_settings
from app.services.device_service import DeviceService


_device_service: DeviceService | None = None


async def get_device_service() -> DeviceService:
    global _device_service
    if _device_service is None:
        _device_service = DeviceService(load_ezviz_settings())
    return _device_service


async def close_device_service() -> None:
    global _device_service
    if _device_service is not None:
        await _device_service.close()
        _device_service = None
