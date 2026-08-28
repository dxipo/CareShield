from contextlib import asynccontextmanager

import secrets
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from careshield_contracts import AlgorithmCapabilities, AlgorithmResult

from app.core.config import load_worker_settings
from app.media.backend_client import BackendMediaClient
from app.publisher.result_publisher import PublishError, ResultPublisher
from app.services.fall_detection_service import FallDetectionService
from app.services.pipeline_test_service import PipelineTestService
from app.services.worker_runtime import WorkerRuntime

settings = load_worker_settings()
publisher = ResultPublisher(settings)
media_client = BackendMediaClient(settings)
fall_detection_service = FallDetectionService(settings, publisher, media_client)
runtime = WorkerRuntime(settings, publisher, fall_detection_service)
pipeline_test_service = PipelineTestService(publisher)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="CareShield AI Worker", version=settings.worker_version, lifespan=lifespan)


def require_internal_credentials(authorization: str | None) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    if not (
        settings.shared_token
        and scheme.lower() == "bearer"
        and secrets.compare_digest(token, settings.shared_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal worker credentials",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-worker"}


@app.get("/capabilities", response_model=AlgorithmCapabilities)
async def capabilities() -> AlgorithmCapabilities:
    return runtime.capabilities


@app.get("/internal/fall-detection/preview.mjpeg")
async def fall_detection_preview(
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    require_internal_credentials(authorization)
    return StreamingResponse(
        fall_detection_service.preview.stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/internal/fall-detection/alert/acknowledge")
async def acknowledge_fall_alert(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    require_internal_credentials(authorization)
    return fall_detection_service.acknowledge_alert()


if settings.development:

    @app.post("/test/publish", response_model=AlgorithmResult)
    async def publish_pipeline_test() -> AlgorithmResult:
        try:
            return await pipeline_test_service.publish()
        except PublishError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
