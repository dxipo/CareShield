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
    )
