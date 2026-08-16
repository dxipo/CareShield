from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.adapters.ezviz.exceptions import (
    EzvizApiError,
    EzvizDeviceNotFoundError,
    EzvizError,
    EzvizNotConfiguredError,
)
from app.api.dependencies import get_device_service
from app.schemas.device import DeviceDetail, DeviceSummary
from app.services.device_service import DeviceService


router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceSummary])
async def list_devices(
    service: Annotated[DeviceService, Depends(get_device_service)],
) -> list[DeviceSummary]:
    try:
        return await service.list_devices()
    except EzvizError as exc:
        raise _to_http_exception(exc) from exc


@router.get("/{device_serial}", response_model=DeviceDetail)
async def get_device(
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[DeviceService, Depends(get_device_service)],
) -> DeviceDetail:
    try:
        return await service.get_device(device_serial)
    except EzvizError as exc:
        raise _to_http_exception(exc) from exc


def _to_http_exception(exc: EzvizError) -> HTTPException:
    if isinstance(exc, EzvizNotConfiguredError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EZVIZ integration is not configured",
        )
    if isinstance(exc, EzvizDeviceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="EZVIZ device was not found",
        )
    if isinstance(exc, EzvizApiError) and exc.code:
        detail = f"EZVIZ API request failed (code {exc.code})"
    else:
        detail = "EZVIZ API request failed"
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
