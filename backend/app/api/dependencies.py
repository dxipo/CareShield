from app.core.config import load_ezviz_settings
from app.services.device_service import DeviceService
from app.services.media_probe_service import MediaProbeService
from app.services.stream_service import StreamService


_device_service: DeviceService | None = None
_stream_service: StreamService | None = None
_media_probe_service: MediaProbeService | None = None


async def get_device_service() -> DeviceService:
    global _device_service
    if _device_service is None:
        _device_service = DeviceService(load_ezviz_settings())
    return _device_service


async def get_stream_service() -> StreamService:
    global _stream_service
    if _stream_service is None:
        _stream_service = StreamService(await get_device_service())
    return _stream_service


async def get_media_probe_service() -> MediaProbeService:
    global _media_probe_service
    if _media_probe_service is None:
        _media_probe_service = MediaProbeService(await get_stream_service())
    return _media_probe_service


async def close_device_service() -> None:
    global _device_service, _stream_service, _media_probe_service
    _media_probe_service = None
    _stream_service = None
    if _device_service is not None:
        await _device_service.close()
        _device_service = None
