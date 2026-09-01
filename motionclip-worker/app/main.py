"""Dependency-minimal internal HTTP server for the isolated model runtime."""

from __future__ import annotations

import json
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID


DATA_ROOT = Path(os.getenv("FALL_RISK_DATA_ROOT", "/data/fall-risk")).resolve()
SHARED_TOKEN = os.getenv("AI_WORKER_SHARED_TOKEN", "").strip()
PROFILE = os.getenv("MOTIONCLIP_PROFILE", "carepd_four_dataset_explainable").strip()
DEVICE = os.getenv("MOTIONCLIP_DEVICE", "auto").strip()
CHECKPOINT = os.getenv(
    "MOTIONCLIP_CHECKPOINT", "/models/motionclip/checkpoint_best.pth.tar"
).strip()
RISK_THRESHOLDS = Path(
    os.getenv(
        "MOTIONCLIP_RISK_THRESHOLDS",
        "/opt/careshield/motionclip-config/carepd_encoder_only_risk_thresholds.json",
    )
).resolve()

from app.model_service import MotionClipService  # noqa: E402


try:
    MODEL = MotionClipService(PROFILE, CHECKPOINT, DEVICE, RISK_THRESHOLDS)
    STARTUP_ERROR: str | None = None
except Exception:
    MODEL = None
    STARTUP_ERROR = "MotionCLIP model could not be loaded"


class Handler(BaseHTTPRequestHandler):
    server_version = "CareShieldMotionCLIP/0.6.0"

    def log_message(self, format: str, *args: object) -> None:
        # Do not log payloads or filesystem paths from internal inference calls.
        if self.command == "GET" and self.path == "/health":
            return
        print(f"motionclip-worker {self.command} {self.path} {args[1] if len(args) > 1 else ''}", flush=True)

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
            SHARED_TOKEN
            and scheme.lower() == "bearer"
            and secrets.compare_digest(token, SHARED_TOKEN)
        )

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        payload: dict[str, object] = {
            "status": "ok" if MODEL is not None else "unavailable",
            "service": "motionclip-worker",
            "ready": MODEL is not None,
        }
        if MODEL is not None:
            payload.update(MODEL.runtime_info)
        elif STARTUP_ERROR:
            payload["message"] = STARTUP_ERROR
        self._json(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/internal/predict/gvhmr":
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
            source = (DATA_ROOT / str(assessment_id) / "gvhmr" / "smplx_global_params.npz").resolve()
            if DATA_ROOT not in source.parents or not source.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"detail": "GVHMR parameters not found"})
                return
            result = MODEL.predict_gvhmr(source)
            self._json(HTTPStatus.OK, result)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"detail": str(exc)[:300]})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": "MotionCLIP inference failed"})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8091), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
