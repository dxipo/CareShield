from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.adapters.ezviz.exceptions import (
    EzvizDeviceNotFoundError,
    EzvizDeviceOfflineError,
    EzvizError,
    EzvizNotConfiguredError,
)
from app.api.dependencies import get_device_service, get_stream_service
from app.api.internal_ai import verify_worker_token
from app.schemas.device import DeviceSummary
from app.schemas.stream import StreamPlayback
from app.services.device_service import DeviceService
from app.services.stream_service import StreamService


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
) -> StreamPlayback:
    """Issue a temporary runtime stream to an authenticated AI Worker."""

    try:
        return await service.get_live_stream(
            device_serial,
            channel_no=channel_no,
            quality=quality,
            protocol="http_flv",
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
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Temporary media stream is unavailable",
    )
