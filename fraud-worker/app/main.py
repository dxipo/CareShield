from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import load_settings
from app.publisher.result_publisher import ResultPublisher
from app.services.fraud_detection_service import FraudDetectionService
from app.services.worker_runtime import WorkerRuntime


settings = load_settings()
publisher = ResultPublisher(settings)
fraud_service = FraudDetectionService(settings, publisher)
runtime = WorkerRuntime(settings, publisher, fraud_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="CareShield Fraud Worker", version=settings.worker_version, lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "fraud-worker",
        "ready": fraud_service.capability == "running",
        "fraud_detection": fraud_service.capability,
    }


@app.get("/capabilities")
async def capabilities() -> dict:
    return runtime.heartbeat_payload().capabilities.model_dump()


@app.get("/status")
async def status() -> dict:
    return fraud_service.runtime_metadata()["fraud_detection"]
