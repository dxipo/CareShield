from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-worker"}


@app.get("/capabilities", response_model=AlgorithmCapabilities)
async def capabilities() -> AlgorithmCapabilities:
    return runtime.capabilities


if settings.development:

    @app.post("/test/publish", response_model=AlgorithmResult)
    async def publish_pipeline_test() -> AlgorithmResult:
        try:
            return await pipeline_test_service.publish()
        except PublishError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
