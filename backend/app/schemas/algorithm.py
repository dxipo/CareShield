from pydantic import BaseModel, ConfigDict

from careshield_contracts import (
    AlgorithmCapabilities,
    AlgorithmResult,
    WorkerHeartbeat,
)


class IngestAcceptedResponse(BaseModel):
    status: str
    result_id: str


class HeartbeatAcceptedResponse(BaseModel):
    status: str
    worker_id: str


class AlgorithmsStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    redis_reachable: bool
    workers: list[WorkerHeartbeat]
    capabilities: AlgorithmCapabilities
    latest_pipeline_test: AlgorithmResult | None
    latest_fall_detection: AlgorithmResult | None
    latest_fraud_detection: AlgorithmResult | None


class SystemStatusResponse(BaseModel):
    backend: str
    redis: str
    ai_worker: str
