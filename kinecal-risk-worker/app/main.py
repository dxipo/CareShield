"""Dependency-minimal internal HTTP server for KINECAL inference."""

from __future__ import annotations

import json
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

from app.model_service import KinecalRiskService


DATA_ROOT = Path(os.getenv("FALL_RISK_DATA_ROOT", "/data/fall-risk")).resolve()
SHARED_TOKEN = os.getenv("AI_WORKER_SHARED_TOKEN", "").strip()
CHECKPOINT = Path(os.getenv(
    "KINECAL_CHECKPOINT", "/models/kinecal/kinecal_walk_v2_best.pt"
)).resolve()
PROFILE = Path(os.getenv(
    "KINECAL_PROFILE", "/opt/careshield/kinecal-config/kinecal_walk_v2.json"
)).resolve()
DEVICE = os.getenv("KINECAL_DEVICE", "auto").strip()

try:
    MODEL = KinecalRiskService(CHECKPOINT, PROFILE, DEVICE)
    STARTUP_ERROR: str | None = None
except Exception:
    MODEL = None
    STARTUP_ERROR = "KINECAL risk model could not be loaded"


class Handler(BaseHTTPRequestHandler):
    server_version = "CareShieldKINECAL/0.8.0"

    def log_message(self, format: str, *args: object) -> None:
        if self.command == "GET" and self.path == "/health":
            return
        print(f"kinecal-risk-worker {self.command} {self.path}", flush=True)

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        return bool(
            SHARED_TOKEN and scheme.lower() == "bearer"
            and secrets.compare_digest(token, SHARED_TOKEN)
        )

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        payload: dict[str, object] = {
            "status": "ok" if MODEL is not None else "unavailable",
            "service": "kinecal-risk-worker",
            "ready": MODEL is not None,
        }
        if MODEL is not None:
            payload.update(MODEL.runtime_info)
        elif STARTUP_ERROR:
            payload["message"] = STARTUP_ERROR
        self._json(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/internal/predict/world-skeleton":
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"detail": "Unauthorized"})
            return
        if MODEL is None:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "Model unavailable"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            assessment_id = UUID(str(body.get("assessment_id", "")))
            source = (DATA_ROOT / str(assessment_id) / "gvhmr" / "world_skeleton_3d.npz").resolve()
            if DATA_ROOT not in source.parents or not source.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"detail": "World skeleton not found"})
                return
            self._json(HTTPStatus.OK, MODEL.predict(source))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(exc)[:300]})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": "KINECAL inference failed"})


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", 8092), Handler).serve_forever()


if __name__ == "__main__":
    main()
