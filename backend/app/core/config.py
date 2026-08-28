import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True, slots=True)
class EzvizSettings:
    app_key: str
    app_secret: str
    api_base_url: str = "https://open.ys7.com"
    timeout_seconds: float = 10.0
    browser_playback_enabled: bool = False
    ezopen_domain: str = "open.ys7.com"

    @property
    def configured(self) -> bool:
        placeholders = {"your_app_key", "your_app_secret"}
        return bool(
            self.app_key
            and self.app_secret
            and self.app_key not in placeholders
            and self.app_secret not in placeholders
        )


def load_ezviz_settings() -> EzvizSettings:
    return EzvizSettings(
        app_key=os.getenv("EZVIZ_APP_KEY", "").strip(),
        app_secret=os.getenv("EZVIZ_APP_SECRET", "").strip(),
        api_base_url=os.getenv(
            "EZVIZ_API_BASE_URL",
            "https://open.ys7.com",
        ).strip().rstrip("/"),
        browser_playback_enabled=os.getenv(
            "EZVIZ_BROWSER_PLAYBACK_ENABLED",
            "false",
        ).strip().lower() in {"1", "true", "yes", "on"},
        ezopen_domain=os.getenv(
            "EZVIZ_EZOPEN_DOMAIN",
            "open.ys7.com",
        ).strip(),
    )


@dataclass(frozen=True, slots=True)
class AiRealtimeSettings:
    app_env: str
    redis_url: str
    shared_token: str
    worker_ttl_seconds: int
    latest_result_ttl_seconds: int
    worker_internal_url: str = "http://ai-worker:8080"

    @property
    def configured(self) -> bool:
        return bool(self.shared_token)

    @property
    def development(self) -> bool:
        return self.app_env.lower() == "development"


def load_ai_realtime_settings() -> AiRealtimeSettings:
    return AiRealtimeSettings(
        app_env=os.getenv("APP_ENV", "development").strip(),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
        shared_token=os.getenv("AI_WORKER_SHARED_TOKEN", "").strip(),
        worker_ttl_seconds=int(os.getenv("AI_WORKER_TTL_SECONDS", "30")),
        latest_result_ttl_seconds=int(
            os.getenv("AI_LATEST_RESULT_TTL_SECONDS", "3600")
        ),
        worker_internal_url=os.getenv(
            "AI_WORKER_INTERNAL_URL",
            "http://ai-worker:8080",
        ).strip().rstrip("/"),
    )
