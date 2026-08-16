from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependencies import close_device_service
from app.api.devices import router as devices_router
from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.streams import router as streams_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_device_service()

app = FastAPI(
    title="Elderly AI Safety Platform API",
    version="0.3.0",
    lifespan=lifespan,
)
app.include_router(health_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(streams_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
