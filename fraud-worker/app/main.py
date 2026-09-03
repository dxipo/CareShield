from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status as http_status

from app.core.config import load_settings
from app.publisher.result_publisher import PublishError, ResultPublisher
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


def require_internal_credentials(authorization: str | None) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    if not (
        settings.shared_token
        and scheme.lower() == "bearer"
        and secrets.compare_digest(token, settings.shared_token)
    ):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal worker credentials",
        )


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


@app.post("/internal/fraud-detection/alert/acknowledge")
async def acknowledge_fraud_alert(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    require_internal_credentials(authorization)
    result = fraud_service.acknowledge_alert()
    try:
        # Publish the acknowledgement immediately so a refreshed browser does
        # not replay the same incident while waiting for the next heartbeat.
        await publisher.heartbeat(runtime.heartbeat_payload())
    except PublishError:
        pass
    return result
