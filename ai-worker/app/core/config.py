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
    fall_model_path: str = "/models/yolo26m-pose.pt"
    fall_model_name: str = "yolo26m-pose.pt"
    fall_person_model_path: str = "/models/yolo26s.pt"
    fall_person_model_name: str = "yolo26s.pt"
    fall_classifier_model_path: str = "/models/fall_detection/stgcn-extend-real440.pth"
    fall_classifier_model_name: str = "stgcn-extend-real440"
    pose_confidence: float = 0.20
    person_confidence: float = 0.20
    media_request_timeout_seconds: float = 10.0
    media_reconnect_seconds: float = 3.0
    media_relay_internal_url: str = ""
    fall_config: FallDetectionConfig = field(default_factory=FallDetectionConfig)

    @property
    def development(self) -> bool:
        return self.app_env.lower() == "development"


def load_worker_settings() -> WorkerSettings:
    fall_config = FallDetectionConfig(
        input_fps=float(os.getenv("FALL_INPUT_FPS", "15")),
        input_size=int(os.getenv("FALL_INPUT_SIZE", "960")),
        minimum_keypoint_confidence=float(
            os.getenv("FALL_MIN_KEYPOINT_CONFIDENCE", "0.35")
        ),
        result_heartbeat_seconds=float(
            os.getenv("FALL_RESULT_HEARTBEAT_SECONDS", "1")
        ),
        significant_score_delta=float(
            os.getenv("FALL_SIGNIFICANT_SCORE_DELTA", "0.15")
        ),
        classifier_inference_hz=float(os.getenv("FALL_CLASSIFIER_INFERENCE_HZ", "2")),
        stgcn_suspected_threshold=float(
            os.getenv("FALL_STGCN_SUSPECTED_THRESHOLD", "0.60")
        ),
        stgcn_fallen_threshold=float(
            os.getenv("FALL_STGCN_FALLEN_THRESHOLD", "0.80")
        ),
        stgcn_confirmation_windows=int(
            os.getenv("FALL_STGCN_CONFIRMATION_WINDOWS", "1")
        ),
        stgcn_recovery_windows=int(os.getenv("FALL_STGCN_RECOVERY_WINDOWS", "5")),
        tracking_minimum_iou=float(os.getenv("FALL_TRACKING_MINIMUM_IOU", "0.25")),
        tracking_maximum_missing_frames=int(
            os.getenv("FALL_TRACKING_MAXIMUM_MISSING_FRAMES", "30")
        ),
        tracking_maximum_center_distance=float(
            os.getenv("FALL_TRACKING_MAXIMUM_CENTER_DISTANCE", "0.45")
        ),
        minimum_sequence_valid_ratio=float(
            os.getenv("FALL_MIN_SEQUENCE_VALID_RATIO", "0.80")
        ),
        observation_window_seconds=float(
            os.getenv("FALL_OBSERVATION_WINDOW_SECONDS", "2.0")
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
            "/models/yolo26m-pose.pt",
        ).strip(),
        fall_model_name=os.getenv("FALL_MODEL_NAME", "yolo26m-pose.pt").strip(),
        fall_person_model_path=os.getenv(
            "FALL_PERSON_MODEL_PATH",
            "/models/yolo26s.pt",
        ).strip(),
        fall_person_model_name=os.getenv(
            "FALL_PERSON_MODEL_NAME",
            "yolo26s.pt",
        ).strip(),
        fall_classifier_model_path=os.getenv(
            "FALL_CLASSIFIER_MODEL_PATH",
            "/models/fall_detection/stgcn-extend-real440.pth",
        ).strip(),
        fall_classifier_model_name=os.getenv(
            "FALL_CLASSIFIER_MODEL_NAME",
            "stgcn-extend-real440",
        ).strip(),
        pose_confidence=float(os.getenv("FALL_POSE_CONFIDENCE", "0.20")),
        person_confidence=float(os.getenv("FALL_PERSON_CONFIDENCE", "0.20")),
        media_request_timeout_seconds=float(
            os.getenv("AI_MEDIA_REQUEST_TIMEOUT_SECONDS", "10")
        ),
        media_reconnect_seconds=float(
            os.getenv("AI_MEDIA_RECONNECT_SECONDS", "3")
        ),
        media_relay_internal_url=os.getenv(
            "MEDIA_RELAY_INTERNAL_URL", ""
        ).strip().rstrip("/"),
        fall_config=fall_config,
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}
