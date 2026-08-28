from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.fall_detection.pose import PosePerson


COCO_LINKS = (
    (0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9),
    (6, 8), (8, 10), (5, 11), (6, 12), (11, 12), (11, 13),
    (13, 15), (12, 14), (14, 16),
)


class AnnotatedPreview:
    """In-memory MJPEG source; no raw frame or playback URL is persisted."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._jpeg: bytes | None = None
        self._version = 0

    async def update(self, jpeg: bytes) -> None:
        async with self._condition:
            self._jpeg = jpeg
            self._version += 1
            self._condition.notify_all()

    async def stream(self) -> AsyncIterator[bytes]:
        version = -1
        while True:
            async with self._condition:
                await self._condition.wait_for(
                    lambda: self._jpeg is not None and self._version != version
                )
                jpeg = self._jpeg
                version = self._version
            if jpeg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"


def render_preview(
    image,
    persons: tuple[PosePerson, ...],
    alert_active: bool,
    *,
    minimum_confidence: float,
    maximum_width: int = 960,
) -> bytes:
    import cv2

    canvas = image.copy()
    height, width = canvas.shape[:2]
    if width > maximum_width:
        scale = maximum_width / width
        canvas = cv2.resize(canvas, (maximum_width, int(height * scale)))
        height, width = canvas.shape[:2]
    for person in persons:
        left = int(person.bbox.x1 * width)
        top = int(person.bbox.y1 * height)
        right = int(person.bbox.x2 * width)
        bottom = int(person.bbox.y2 * height)
        cv2.rectangle(canvas, (left, top), (right, bottom), (70, 220, 140), 2)
        cv2.putText(
            canvas,
            person.person_id,
            (left, max(22, top - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (70, 220, 140),
            2,
        )
        points = person.keypoints
        if len(points) < 17:
            cv2.putText(
                canvas,
                "PERSON / POSE UNAVAILABLE",
                (left, min(height - 10, bottom + 22)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 170, 255),
                1,
            )
            continue
        for start, end in COCO_LINKS:
            if points[start].confidence < minimum_confidence or points[end].confidence < minimum_confidence:
                continue
            first = (int(points[start].x * width), int(points[start].y * height))
            second = (int(points[end].x * width), int(points[end].y * height))
            cv2.line(canvas, first, second, (80, 230, 150), 2, cv2.LINE_AA)
        for point in points:
            if point.confidence >= minimum_confidence:
                cv2.circle(
                    canvas,
                    (int(point.x * width), int(point.y * height)),
                    3,
                    (0, 170, 255),
                    -1,
                    cv2.LINE_AA,
                )
    if alert_active:
        cv2.rectangle(canvas, (0, 0), (width, 58), (25, 25, 210), -1)
        cv2.putText(
            canvas,
            "FALL DETECTED",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            3,
        )
    success, encoded = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not success:
        raise RuntimeError("Annotated preview encoding failed")
    return encoded.tobytes()
