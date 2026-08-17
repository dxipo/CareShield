import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.fall_detection.config import FallDetectionConfig


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
    fall_enabled: bool = True
    ai_device: str = "auto"
    fall_device_serial: str = ""
    fall_channel_no: int = 1
    fall_model_path: str = "/models/yolo26n-pose.pt"
    fall_model_name: str = "yolo26n-pose.pt"
    pose_confidence: float = 0.35
    media_request_timeout_seconds: float = 10.0
    media_reconnect_seconds: float = 3.0
    fall_config: FallDetectionConfig = field(default_factory=FallDetectionConfig)

    @property
    def development(self) -> bool:
        return self.app_env.lower() == "development"


def load_worker_settings() -> WorkerSettings:
    fall_config = FallDetectionConfig(
        input_fps=float(os.getenv("FALL_INPUT_FPS", "5")),
        input_size=int(os.getenv("FALL_INPUT_SIZE", "640")),
        minimum_keypoint_confidence=float(
            os.getenv("FALL_MIN_KEYPOINT_CONFIDENCE", "0.35")
        ),
        suspected_torso_angle_degrees=float(
            os.getenv("FALL_SUSPECTED_TORSO_ANGLE", "45")
        ),
        fallen_torso_angle_degrees=float(
            os.getenv("FALL_FALLEN_TORSO_ANGLE", "65")
        ),
        downward_velocity_threshold=float(
            os.getenv("FALL_DOWNWARD_VELOCITY", "0.35")
        ),
        lying_aspect_ratio_threshold=float(
            os.getenv("FALL_LYING_ASPECT_RATIO", "1.15")
        ),
        suspected_timeout_seconds=float(
            os.getenv("FALL_SUSPECTED_TIMEOUT_SECONDS", "1.5")
        ),
        fallen_persistence_seconds=float(
            os.getenv("FALL_FALLEN_PERSISTENCE_SECONDS", "1.2")
        ),
        recovery_persistence_seconds=float(
            os.getenv("FALL_RECOVERY_PERSISTENCE_SECONDS", "1.5")
        ),
        result_heartbeat_seconds=float(
            os.getenv("FALL_RESULT_HEARTBEAT_SECONDS", "1")
        ),
        significant_score_delta=float(
            os.getenv("FALL_SIGNIFICANT_SCORE_DELTA", "0.15")
        ),
    )
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
        fall_enabled=_env_bool("FALL_DETECTION_ENABLED", True),
        ai_device=os.getenv("AI_DEVICE", "auto").strip().lower(),
        fall_device_serial=os.getenv("FALL_DEVICE_SERIAL", "").strip(),
        fall_channel_no=int(os.getenv("FALL_CHANNEL_NO", "1")),
        fall_model_path=os.getenv(
            "FALL_MODEL_PATH",
            "/models/yolo26n-pose.pt",
        ).strip(),
        fall_model_name=os.getenv("FALL_MODEL_NAME", "yolo26n-pose.pt").strip(),
        pose_confidence=float(os.getenv("FALL_POSE_CONFIDENCE", "0.35")),
        media_request_timeout_seconds=float(
            os.getenv("AI_MEDIA_REQUEST_TIMEOUT_SECONDS", "10")
        ),
        media_reconnect_seconds=float(
            os.getenv("AI_MEDIA_RECONNECT_SECONDS", "3")
        ),
        fall_config=fall_config,
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}
