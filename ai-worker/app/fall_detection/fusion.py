from __future__ import annotations

from app.fall_detection.pose import PersonDetection, PosePerson


def fuse_person_detections(
    detections: tuple[PersonDetection, ...],
    poses: tuple[PosePerson, ...],
    minimum_iou: float = 0.05,
) -> tuple[PosePerson, ...]:
    """Attach pose keypoints to independent person boxes without inventing joints."""

    fused: list[PosePerson] = []
    used_poses: set[int] = set()
    for index, detection in enumerate(detections, start=1):
        # A detector can briefly split one falling body into several person
        # boxes. Once a pose has claimed that body, suppress further boxes that
        # geometrically describe the same pose instead of rendering duplicates.
        if any(
            _is_match(
                _match_metrics(detection.bbox, poses[pose_index].bbox),
                minimum_iou,
            )
            for pose_index in used_poses
        ):
            continue
        candidates = [
            (pose_index, _match_metrics(detection.bbox, pose.bbox))
            for pose_index, pose in enumerate(poses)
            if pose_index not in used_poses
        ]
        best = max(
            candidates,
            key=lambda item: (
                item[1][0],
                item[1][1],
                -item[1][2],
            ),
            default=None,
        )
        keypoints = ()
        if best is not None and _is_match(best[1], minimum_iou):
            used_poses.add(best[0])
            keypoints = poses[best[0]].keypoints
        fused.append(
            PosePerson(
                person_id=f"detected-{index}",
                bbox=detection.bbox,
                bbox_confidence=detection.confidence,
                keypoints=keypoints,
            )
        )

    for pose_index, pose in enumerate(poses):
        if pose_index not in used_poses and not any(
            _is_match(_match_metrics(detection.bbox, pose.bbox), minimum_iou)
            for detection in detections
        ):
            fused.append(pose)
    return tuple(fused)


def _iou(first, second) -> float:
    left = max(first.x1, second.x1)
    top = max(first.y1, second.y1)
    right = min(first.x2, second.x2)
    bottom = min(first.y2, second.y2)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union > 0 else 0.0


def _match_metrics(first, second) -> tuple[float, float, float]:
    left = max(first.x1, second.x1)
    top = max(first.y1, second.y1)
    right = min(first.x2, second.x2)
    bottom = min(first.y2, second.y2)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    smaller_area = min(first.width * first.height, second.width * second.height)
    containment = intersection / smaller_area if smaller_area > 0 else 0.0
    first_center = ((first.x1 + first.x2) / 2, (first.y1 + first.y2) / 2)
    second_center = ((second.x1 + second.x2) / 2, (second.y1 + second.y2) / 2)
    distance = (
        (first_center[0] - second_center[0]) ** 2
        + (first_center[1] - second_center[1]) ** 2
    ) ** 0.5
    return _iou(first, second), containment, distance


def _is_match(metrics: tuple[float, float, float], minimum_iou: float) -> bool:
    overlap, containment, center_distance = metrics
    return (
        overlap >= minimum_iou
        or containment >= 0.30
        or center_distance <= 0.25
    )
