import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.api.dependencies import get_ai_realtime_service
from app.main import app


class RecordingService:
    def __init__(self) -> None:
        self.results = []
        self.heartbeats = []

    async def ingest_result(self, result):
        self.results.append(result)

    async def record_heartbeat(self, heartbeat):
        self.heartbeats.append(heartbeat)


def result_payload() -> dict:
    return {
        "result_id": str(uuid4()),
        "task": "pipeline_test",
        "model_id": "pipeline-tester",
        "model_version": "1.0",
        "device_id": None,
        "source_timestamp": None,
        "result_timestamp": datetime.now(timezone.utc).isoformat(),
        "label": "pipeline_ok",
        "score": None,
        "level": None,
        "latency_ms": None,
        "metadata": {"message": "test"},
        "simulated": True,
    }


def request(path: str, token: str | None, payload: dict) -> httpx.Response:
    async def send() -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path, headers=headers, json=payload)

    return asyncio.run(send())


def test_internal_result_ingest_requires_and_accepts_valid_token(monkeypatch) -> None:
    service = RecordingService()
    async def override_service():
        return service
    app.dependency_overrides[get_ai_realtime_service] = override_service
    monkeypatch.setenv("AI_WORKER_SHARED_TOKEN", "unit-test-token")
    try:
        response = request("/internal/ai/results", "unit-test-token", result_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert "unit-test-token" not in response.text
    assert len(service.results) == 1


def test_internal_result_ingest_rejects_invalid_token_without_leaking_it(monkeypatch) -> None:
    service = RecordingService()
    async def override_service():
        return service
    app.dependency_overrides[get_ai_realtime_service] = override_service
    monkeypatch.setenv("AI_WORKER_SHARED_TOKEN", "expected-token")
    try:
        response = request("/internal/ai/results", "wrong-token", result_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "wrong-token" not in response.text
    assert "expected-token" not in response.text
    assert service.results == []


def test_internal_result_ingest_is_unavailable_when_not_configured(monkeypatch) -> None:
    service = RecordingService()
    async def override_service():
        return service
    app.dependency_overrides[get_ai_realtime_service] = override_service
    monkeypatch.delenv("AI_WORKER_SHARED_TOKEN", raising=False)
    try:
        response = request("/internal/ai/results", None, result_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert service.results == []


def test_internal_heartbeat_is_authenticated(monkeypatch) -> None:
    service = RecordingService()
    async def override_service():
        return service
    app.dependency_overrides[get_ai_realtime_service] = override_service
    monkeypatch.setenv("AI_WORKER_SHARED_TOKEN", "unit-test-token")
    payload = {
        "worker_id": "worker-test",
        "online": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.4.0",
        "capabilities": {
            "fall_detection": "not_installed",
            "fall_risk": "not_installed",
            "fraud_detection": "not_installed",
        },
    }
    try:
        response = request("/internal/ai/heartbeat", "unit-test-token", payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "worker_id": "worker-test"}
    assert len(service.heartbeats) == 1
