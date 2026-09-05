"""RGB video screening and temporal normalization."""

from .detectors import YoloPersonDetector
from .normalize import NormalizedVideo, write_cfr_segment
from .segmentation import MotionWalkingSegmenter, Segment, VideoMetadata, read_video_metadata

__all__ = [
    "MotionWalkingSegmenter",
    "NormalizedVideo",
    "Segment",
    "VideoMetadata",
    "YoloPersonDetector",
    "read_video_metadata",
    "write_cfr_segment",
]
