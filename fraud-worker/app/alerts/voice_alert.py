from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import FraudWorkerSettings


class FraudVoiceAlert:
    """Send one camera announcement per fraud-alert lifecycle.

    The audio remains an operator-managed local file. EZVIZ credentials stay in
    Backend, and failures here never change the fraud detection result.
    """

    MAX_AUDIO_BYTES = 5 * 1024 * 1024
    SUPPORTED_SUFFIXES = {".wav", ".mp3", ".aac"}

    def __init__(
        self,
        settings: FraudWorkerSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.enabled = settings.voice_alert_enabled
        self.audio_path = (
            Path(settings.voice_alert_audio_path)
            if settings.voice_alert_audio_path
            else None
        )
        self.channel_no = settings.voice_alert_channel_no
        self.cooldown_seconds = settings.voice_alert_cooldown_seconds
        self.status = "disabled" if not self.enabled else "not_configured"
        self.last_error: str | None = None
        self.last_attempt_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self._alert_latched = False
        self._last_attempt_monotonic: float | None = None
        self._client = httpx.AsyncClient(
            base_url=settings.backend_internal_url,
            headers={"Authorization": f"Bearer {settings.shared_token}"},
            timeout=settings.request_timeout_seconds,
            transport=transport,
            trust_env=False,
        )
        self._refresh_configuration_status()

    @property
    def configured(self) -> bool:
        return self._validated_audio_path() is not None

    async def handle_decision(
        self,
        *,
        device_id: str | None,
        alert_active: bool,
    ) -> bool:
        if not alert_active:
            self._alert_latched = False
            if self.enabled and self.configured:
                self.status = "armed"
            return False
        if not self.enabled:
            self.status = "disabled"
            return False
        if self._alert_latched:
            return False

        # Latch before I/O so repeated warning/critical results cannot generate
        # concurrent billable requests during the same alert lifecycle.
        self._alert_latched = True
        audio_path = self._validated_audio_path()
        if audio_path is None:
            self.status = "not_configured"
            self.last_error = "Fraud voice alert audio is not configured"
            return False
        if not device_id:
            self.status = "unavailable"
            self.last_error = "Fraud voice alert has no target device"
            return False

        now = time.monotonic()
        if (
            self._last_attempt_monotonic is not None
            and now - self._last_attempt_monotonic < self.cooldown_seconds
        ):
            self.status = "cooldown"
            return False

        self._last_attempt_monotonic = now
        self.last_attempt_at = datetime.now(timezone.utc)
        try:
            # Alert files are capped at 5 MB; one bounded local read avoids
            # introducing a thread-pool dependency into the alert path.
            content = audio_path.read_bytes()
            if not content or len(content) > self.MAX_AUDIO_BYTES:
                raise OSError("Voice alert audio size is invalid")
            response = await self._client.post(
                f"/internal/media/devices/{device_id}/voice",
                params={"filename": audio_path.name, "channel_no": self.channel_no},
                content=content,
                headers={"Content-Type": "application/octet-stream"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.status = self._rejection_status(exc.response)
            self.last_error = (
                f"Voice alert request rejected ({exc.response.status_code})"
            )
            return False
        except (httpx.HTTPError, OSError):
            self.status = "failed"
            self.last_error = "Fraud voice alert delivery failed"
            return False

        self.status = "sent"
        self.last_error = None
        self.last_success_at = datetime.now(timezone.utc)
        return True

    def metadata(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "status": self.status,
            "channel_no": self.channel_no,
            "cooldown_seconds": self.cooldown_seconds,
            "last_attempt_at": (
                self.last_attempt_at.isoformat() if self.last_attempt_at else None
            ),
            "last_success_at": (
                self.last_success_at.isoformat() if self.last_success_at else None
            ),
            "last_error": self.last_error,
        }

    async def close(self) -> None:
        await self._client.aclose()

    def _refresh_configuration_status(self) -> None:
        if self.enabled and self.configured:
            self.status = "armed"

    def _validated_audio_path(self) -> Path | None:
        path = self.audio_path
        if (
            path is None
            or path.suffix.lower() not in self.SUPPORTED_SUFFIXES
            or not path.is_file()
        ):
            return None
        return path

    @staticmethod
    def _rejection_status(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return "failed"
        if (
            response.status_code == 503
            and isinstance(payload, dict)
            and payload.get("detail") == "EZVIZ voice broadcast quota is unavailable"
        ):
            return "quota_unavailable"
        return "failed"
