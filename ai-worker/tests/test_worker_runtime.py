from app.core.config import WorkerSettings
from app.services.worker_runtime import WorkerRuntime


class UnusedPublisher:
    pass


def test_heartbeat_truthfully_reports_worker_and_uninstalled_capabilities() -> None:
    settings = WorkerSettings(
        app_env="development",
        backend_internal_url="http://backend.test",
        shared_token="test-token",
        worker_id="worker-test",
        worker_version="0.4.0",
        heartbeat_interval_seconds=10,
        request_timeout_seconds=5,
    )
    heartbeat = WorkerRuntime(settings, UnusedPublisher()).heartbeat_payload()

    assert heartbeat.worker_id == "worker-test"
    assert heartbeat.online is True
    assert heartbeat.capabilities.fall_detection == "not_installed"
