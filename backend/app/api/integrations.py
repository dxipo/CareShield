from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_device_service
from app.schemas.device import EzvizIntegrationStatus
from app.services.device_service import DeviceService


router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/ezviz/status", response_model=EzvizIntegrationStatus)
async def get_ezviz_status(
    service: Annotated[DeviceService, Depends(get_device_service)],
) -> EzvizIntegrationStatus:
    return await service.integration_status()
