from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.adapters.ezviz.exceptions import (
    EzvizApiError,
    EzvizBrowserPlaybackDisabledError,
    EzvizDeviceNotFoundError,
    EzvizDeviceOfflineError,
    EzvizError,
    EzvizNotConfiguredError,
    EzvizStreamUnavailableError,
)
from app.api.dependencies import get_media_probe_service, get_stream_service
from app.schemas.stream import BrowserPlaybackSession, MediaInfo, StreamPlayback
from app.services.media_probe_service import MediaProbeError, MediaProbeService
from app.services.stream_service import StreamService


router = APIRouter(prefix="/devices", tags=["streams"])


@router.get("/{device_serial}/stream", response_model=StreamPlayback)
async def get_live_stream(
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[StreamService, Depends(get_stream_service)],
    channel_no: Annotated[int, Query(ge=1, le=64)] = 1,
    quality: Literal["high", "fluent"] = "high",
) -> StreamPlayback:
    try:
        return await service.get_live_stream(
            device_serial,
            channel_no=channel_no,
            quality=quality,
        )
    except EzvizError as exc:
        raise _stream_http_exception(exc) from exc


@router.get(
    "/{device_serial}/browser-playback",
    response_model=BrowserPlaybackSession,
)
async def get_browser_playback(
    response: Response,
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[StreamService, Depends(get_stream_service)],
    channel_no: Annotated[int, Query(ge=1, le=64)] = 1,
) -> BrowserPlaybackSession:
    # The official EZOPEN Web SDK requires these runtime credentials. Prevent
    # browsers and intermediaries from retaining them after the player session.
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    try:
        return await service.get_browser_playback_session(
            device_serial,
            channel_no=channel_no,
        )
    except EzvizError as exc:
        raise _stream_http_exception(exc) from exc


@router.get("/{device_serial}/media-info", response_model=MediaInfo)
async def get_media_info(
    device_serial: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[MediaProbeService, Depends(get_media_probe_service)],
    channel_no: Annotated[int, Query(ge=1, le=64)] = 1,
) -> MediaInfo:
    try:
        return await service.probe(device_serial, channel_no=channel_no)
    except EzvizError as exc:
        raise _stream_http_exception(exc) from exc
    except MediaProbeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


def _stream_http_exception(exc: EzvizError) -> HTTPException:
    if isinstance(exc, EzvizBrowserPlaybackDisabledError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EZVIZ browser playback is disabled",
        )
    if isinstance(exc, EzvizNotConfiguredError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EZVIZ integration is not configured",
        )
    if isinstance(exc, EzvizDeviceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="EZVIZ device or channel was not found",
        )
    if isinstance(exc, EzvizDeviceOfflineError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EZVIZ device is offline",
        )
    if isinstance(exc, EzvizStreamUnavailableError) and exc.code:
        detail = f"EZVIZ live stream is unavailable (code {exc.code})"
    elif isinstance(exc, EzvizApiError) and exc.code:
        detail = f"EZVIZ API request failed (code {exc.code})"
    else:
        detail = "EZVIZ live stream is unavailable"
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
