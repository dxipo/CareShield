import cv2
import numpy as np

from app.fall_detection.preview import render_preview


def decode(value: bytes):
    return cv2.imdecode(np.frombuffer(value, dtype=np.uint8), cv2.IMREAD_COLOR)


def test_fall_banner_depends_only_on_latched_alert() -> None:
    image = np.zeros((100, 240, 3), dtype=np.uint8)

    acknowledged = decode(
        render_preview(image, (), False, minimum_confidence=0.35)
    )
    active = decode(render_preview(image, (), True, minimum_confidence=0.35))

    assert int(acknowledged[10, 10, 2]) < 50
    assert int(active[10, 10, 2]) > 150
