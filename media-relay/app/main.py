from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.core.config import load_settings
from app.services.relay import RelayService


settings = load_settings()
relay = RelayService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await relay.start()
    yield
    await relay.close()


app = FastAPI(title="CareShield Media Relay", version="0.1.0", lifespan=lifespan)


def verify_internal_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = f"Bearer {settings.shared_token}"
    if not settings.shared_token or not authorization or not hmac.compare_digest(
        authorization, expected
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    snapshot = relay.snapshot()
    return {
        "status": "ok",
        "service": "media-relay",
        "stream_ready": snapshot.ready,
    }


@app.get("/stream", dependencies=[Depends(verify_internal_token)])
async def stream() -> dict:
    return asdict(relay.snapshot())
