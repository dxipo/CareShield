from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FallRiskWorkerSettings:
    backend_internal_url: str
    shared_token: str
    worker_id: str
    worker_version: str
    heartbeat_interval_seconds: int
    data_root: Path
    channel_no: int
    visionmd_python: str
    visionmd_runner: Path
    visionmd_project_root: Path
    visionmd_metrabs_model_dir: Path
    gvhmr_python: str
    gvhmr_runner: Path
    gvhmr_project_root: Path
    gvhmr_checkpoints_root: Path
    gvhmr_body_models_root: Path
    motionclip_internal_url: str = ""
    kinecal_internal_url: str = ""
    media_relay_internal_url: str = ""
    media_relay_playback_url: str = ""
    risk_explanation_enabled: bool = False
    risk_explanation_base_url: str = ""
    risk_explanation_model: str = "qwen3:4b"
    risk_explanation_timeout_seconds: float = 12.0


def load_settings() -> FallRiskWorkerSettings:
    return FallRiskWorkerSettings(
        backend_internal_url=os.getenv(
            "BACKEND_INTERNAL_URL", "http://backend:8000"
        ).strip().rstrip("/"),
        shared_token=os.getenv("AI_WORKER_SHARED_TOKEN", "").strip(),
        worker_id=os.getenv("FALL_RISK_WORKER_ID", "careshield-fall-risk-1").strip(),
        worker_version=os.getenv("FALL_RISK_WORKER_VERSION", "0.6.1").strip(),
        heartbeat_interval_seconds=int(
            os.getenv("AI_WORKER_HEARTBEAT_INTERVAL_SECONDS", "10")
        ),
        data_root=Path(os.getenv("FALL_RISK_DATA_ROOT", "/data/fall-risk")),
        channel_no=int(os.getenv("FALL_RISK_CHANNEL_NO", "1")),
        visionmd_python=os.getenv("VISIONMD_PYTHON", "/opt/visionmd-env/bin/python"),
        visionmd_runner=Path(
            os.getenv("VISIONMD_RUNNER", "/opt/visionmd-app/run_rgb_to_28.py")
        ),
        visionmd_project_root=Path(
            os.getenv("VISIONMD_PROJECT_ROOT", "/opt/visionmd-app")
        ),
        visionmd_metrabs_model_dir=Path(
            os.getenv(
                "VISIONMD_METRABS_MODEL_DIR",
                "/models/fall-risk/visionmd/metrabs_local_s",
            )
        ),
        gvhmr_python=os.getenv("GVHMR_PYTHON", "/opt/gvhmr-env/bin/python"),
        gvhmr_runner=Path(
            os.getenv("GVHMR_RUNNER", "/opt/careshield/gvhmr/run_gvhmr_world.py")
        ),
        gvhmr_project_root=Path(os.getenv("GVHMR_PROJECT_ROOT", "/opt/gvhmr")),
        gvhmr_checkpoints_root=Path(
            os.getenv(
                "GVHMR_CHECKPOINTS_ROOT",
                "/models/fall-risk/gvhmr/official-checkpoints",
            )
        ),
        gvhmr_body_models_root=Path(
            os.getenv(
                "GVHMR_BODY_MODELS_ROOT",
                "/models/fall-risk/gvhmr/body_models",
            )
        ),
        motionclip_internal_url=os.getenv(
            "MOTIONCLIP_INTERNAL_URL", "http://motionclip-worker:8091"
        ).strip().rstrip("/"),
        kinecal_internal_url=os.getenv(
            "KINECAL_INTERNAL_URL", "http://kinecal-risk-worker:8092"
        ).strip().rstrip("/"),
        media_relay_internal_url=os.getenv(
            "MEDIA_RELAY_INTERNAL_URL", ""
        ).strip().rstrip("/"),
        media_relay_playback_url=os.getenv(
            "MEDIA_RELAY_PLAYBACK_URL", ""
        ).strip().rstrip("/"),
        risk_explanation_enabled=os.getenv(
            "FALL_RISK_LLM_EXPLANATION_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"},
        risk_explanation_base_url=os.getenv(
            "FALL_RISK_OLLAMA_BASE_URL", "http://ollama:11434"
        ).strip().rstrip("/"),
        risk_explanation_model=os.getenv(
            "FALL_RISK_OLLAMA_MODEL", "qwen3:4b"
        ).strip(),
        risk_explanation_timeout_seconds=float(
            os.getenv("FALL_RISK_LLM_TIMEOUT_SECONDS", "12")
        ),
    )
