from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Normalized xyxy coordinates in the source image."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)


@dataclass(frozen=True, slots=True)
class PoseKeypoint:
    name: str
    x: float
    y: float
    confidence: float


@dataclass(frozen=True, slots=True)
class PosePerson:
    person_id: str
    bbox: BoundingBox
    bbox_confidence: float
    keypoints: tuple[PoseKeypoint, ...]

    @property
    def mean_keypoint_confidence(self) -> float:
        visible = [point.confidence for point in self.keypoints if point.confidence > 0]
        return sum(visible) / len(visible) if visible else 0.0

    def keypoint(self, name: str) -> PoseKeypoint | None:
        return next((point for point in self.keypoints if point.name == name), None)


@dataclass(frozen=True, slots=True)
class PersonDetection:
    bbox: BoundingBox
    confidence: float


@dataclass(frozen=True, slots=True)
class PersonDetectionFrame:
    timestamp: datetime
    detections: tuple[PersonDetection, ...]
    inference_ms: float


@dataclass(frozen=True, slots=True)
class PoseFrame:
    timestamp: datetime
    source_width: int
    source_height: int
    persons: tuple[PosePerson, ...]
    inference_ms: float

    @property
    def primary_person(self) -> PosePerson | None:
        return max(self.persons, key=lambda person: person.bbox_confidence, default=None)


def pose_is_reliable(
    person: PosePerson,
    minimum_confidence: float,
    minimum_keypoints: int = 6,
) -> bool:
    """Require enough usable joints before a pose can reach the classifier."""

    reliable_points = sum(
        point.confidence >= minimum_confidence for point in person.keypoints
    )
    return (
        reliable_points >= minimum_keypoints
        and person.mean_keypoint_confidence >= minimum_confidence
    )
