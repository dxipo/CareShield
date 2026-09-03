from app.core.config import load_ai_realtime_settings, load_ezviz_settings
from app.services.ai_realtime_service import AiRealtimeService
from app.services.device_service import DeviceService
from app.services.fall_risk_service import FallRiskService
from app.services.media_probe_service import MediaProbeService
from app.services.realtime_hub import RealtimeHub
from app.services.realtime_store import RealtimeStore
from app.services.stream_service import StreamService
from app.services.voice_broadcast_service import VoiceBroadcastService


_device_service: DeviceService | None = None
_stream_service: StreamService | None = None
_media_probe_service: MediaProbeService | None = None
_realtime_hub = RealtimeHub()
_ai_realtime_service: AiRealtimeService | None = None
_fall_risk_service: FallRiskService | None = None
_voice_broadcast_service: VoiceBroadcastService | None = None


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


async def get_voice_broadcast_service() -> VoiceBroadcastService:
    global _voice_broadcast_service
    if _voice_broadcast_service is None:
        _voice_broadcast_service = VoiceBroadcastService(await get_device_service())
    return _voice_broadcast_service


async def get_realtime_hub() -> RealtimeHub:
    return _realtime_hub


async def get_ai_realtime_service() -> AiRealtimeService:
    global _ai_realtime_service
    if _ai_realtime_service is None:
        store = RealtimeStore(load_ai_realtime_settings())
        _ai_realtime_service = AiRealtimeService(store, _realtime_hub)
    return _ai_realtime_service


async def get_fall_risk_service() -> FallRiskService:
    global _fall_risk_service
    if _fall_risk_service is None:
        _fall_risk_service = FallRiskService(load_ai_realtime_settings())
    return _fall_risk_service


async def close_device_service() -> None:
    global _device_service, _stream_service, _media_probe_service
    global _voice_broadcast_service
    _media_probe_service = None
    _stream_service = None
    _voice_broadcast_service = None
    if _device_service is not None:
        await _device_service.close()
        _device_service = None


async def close_ai_realtime_service() -> None:
    global _ai_realtime_service, _fall_risk_service
    if _ai_realtime_service is not None:
        await _ai_realtime_service.close()
        _ai_realtime_service = None
    if _fall_risk_service is not None:
        await _fall_risk_service.close()
        _fall_risk_service = None
