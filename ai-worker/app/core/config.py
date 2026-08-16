import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    app_env: str
    backend_internal_url: str
    shared_token: str
    worker_id: str
    worker_version: str
    heartbeat_interval_seconds: float
    request_timeout_seconds: float

    @property
    def development(self) -> bool:
        return self.app_env.lower() == "development"


def load_worker_settings() -> WorkerSettings:
    return WorkerSettings(
        app_env=os.getenv("APP_ENV", "development").strip(),
        backend_internal_url=os.getenv(
            "BACKEND_INTERNAL_URL",
            "http://localhost:8000",
        ).strip().rstrip("/"),
        shared_token=os.getenv("AI_WORKER_SHARED_TOKEN", "").strip(),
        worker_id=os.getenv("AI_WORKER_ID", "careshield-worker-1").strip(),
        worker_version=os.getenv("AI_WORKER_VERSION", "0.4.0").strip(),
        heartbeat_interval_seconds=float(
            os.getenv("AI_WORKER_HEARTBEAT_INTERVAL_SECONDS", "10")
        ),
        request_timeout_seconds=float(
            os.getenv("AI_WORKER_REQUEST_TIMEOUT_SECONDS", "5")
        ),
    )
