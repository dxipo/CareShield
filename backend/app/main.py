from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.algorithms import router as algorithms_router
from app.api.dependencies import close_ai_realtime_service, close_device_service
from app.api.devices import router as devices_router
from app.api.fall_detection import router as fall_detection_router
from app.api.health import router as health_router
from app.api.internal_ai import router as internal_ai_router
from app.api.internal_media import router as internal_media_router
from app.api.integrations import router as integrations_router
from app.api.realtime import router as realtime_router
from app.api.streams import router as streams_router
from app.api.system import router as system_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_device_service()
    await close_ai_realtime_service()

app = FastAPI(
    title="Elderly AI Safety Platform API",
    version="0.5.0",
    lifespan=lifespan,
)
app.include_router(health_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(fall_detection_router, prefix="/api")
app.include_router(streams_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(algorithms_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(internal_ai_router)
app.include_router(internal_media_router)
app.include_router(realtime_router)
