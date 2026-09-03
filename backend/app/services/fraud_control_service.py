from __future__ import annotations

import httpx

from app.core.config import AiRealtimeSettings


class FraudControlUnavailableError(RuntimeError):
    pass


class FraudControlService:
    """Forward authenticated operator actions to the isolated Fraud Worker."""

    def __init__(
        self,
        settings: AiRealtimeSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def acknowledge_alert(self) -> dict[str, bool]:
        headers = {"Authorization": f"Bearer {self._settings.shared_token}"}
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.fraud_worker_internal_url,
                headers=headers,
                timeout=5,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/internal/fraud-detection/alert/acknowledge"
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise FraudControlUnavailableError(
                "Fraud alert could not be acknowledged"
            ) from exc
