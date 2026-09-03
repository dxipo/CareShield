from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status

from app.adapters.ezviz.exceptions import (
    EzvizDeviceNotFoundError,
    EzvizDeviceOfflineError,
    EzvizError,
    EzvizNotConfiguredError,
    EzvizVoiceUnsupportedError,
    EzvizVoiceQuotaError,
    EzvizVoiceValidationError,
)
from app.api.dependencies import (
    get_device_service,
    get_stream_service,
    get_voice_broadcast_service,
)
from app.api.internal_ai import verify_worker_token
from app.schemas.device import DeviceSummary
from app.schemas.stream import StreamPlayback
from app.schemas.voice import VoiceBroadcastCapability, VoiceBroadcastResult
from app.services.device_service import DeviceService
from app.services.stream_service import StreamService
from app.services.voice_broadcast_service import VoiceBroadcastService


router = APIRouter(
    prefix="/internal/media",
    tags=["internal-media"],
    dependencies=[Depends(verify_worker_token)],
)


@router.get("/devices", response_model=list[DeviceSummary])
async def list_media_devices(
    service: Annotated[DeviceService, Depends(get_device_service)],
) -> list[DeviceSummary]:
    """Return standardized devices to the trusted Worker, never EZVIZ credentials."""

    try:
        return await service.list_devices()
    except EzvizError as exc:
        raise _internal_media_exception(exc) from exc


@router.get("/devices/{device_serial}/stream", response_model=StreamPlayback)
async def get_worker_stream(
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[StreamService, Depends(get_stream_service)],
    channel_no: Annotated[int, Query(ge=1, le=64)] = 1,
    quality: Literal["high", "fluent"] = "high",
    protocol: Literal["hls", "http_flv"] = "http_flv",
) -> StreamPlayback:
    """Issue a temporary runtime stream to an authenticated Worker.

    Realtime inference explicitly uses HTTP-FLV. Batch assessment can request
    HLS so it does not compete for the realtime transport session.
    """

    try:
        return await service.get_live_stream(
            device_serial,
            channel_no=channel_no,
            quality=quality,
            protocol=protocol,
        )
    except EzvizError as exc:
        raise _internal_media_exception(exc) from exc


@router.get(
    "/devices/{device_serial}/voice/capability",
    response_model=VoiceBroadcastCapability,
)
async def get_voice_capability(
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[VoiceBroadcastService, Depends(get_voice_broadcast_service)],
    channel_no: Annotated[int, Query(ge=1, le=64)] = 1,
) -> VoiceBroadcastCapability:
    try:
        return await service.capability(device_serial, channel_no=channel_no)
    except EzvizError as exc:
        raise _internal_media_exception(exc) from exc


@router.post(
    "/devices/{device_serial}/voice",
    response_model=VoiceBroadcastResult,
)
async def send_voice_once(
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    audio: Annotated[bytes, Body(media_type="application/octet-stream")],
    service: Annotated[VoiceBroadcastService, Depends(get_voice_broadcast_service)],
    filename: Annotated[str, Query(min_length=1, max_length=128)],
    channel_no: Annotated[int, Query(ge=1, le=64)] = 1,
) -> VoiceBroadcastResult:
    """Forward transient audio to EZVIZ without persisting it."""

    try:
        return await service.send_once(
            device_serial,
            channel_no=channel_no,
            filename=filename,
            content=audio,
        )
    except EzvizError as exc:
        raise _internal_media_exception(exc) from exc


def _internal_media_exception(exc: EzvizError) -> HTTPException:
    if isinstance(exc, EzvizNotConfiguredError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media integration is not configured",
        )
    if isinstance(exc, EzvizDeviceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media device or channel was not found",
        )
    if isinstance(exc, EzvizDeviceOfflineError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media device is offline",
        )
    if isinstance(exc, EzvizVoiceValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Voice audio is invalid",
        )
    if isinstance(exc, EzvizVoiceUnsupportedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Media device does not support voice broadcast",
        )
    if isinstance(exc, EzvizVoiceQuotaError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EZVIZ voice broadcast quota is unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Temporary media stream is unavailable",
    )
