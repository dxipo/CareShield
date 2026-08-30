from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from careshield_contracts import FallRiskAssessment


class AssessmentNotFoundError(KeyError):
    pass


class AssessmentStore:
    """Small manifest store; media and NPZ artifacts remain on the same volume."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def directory(self, assessment_id: UUID) -> Path:
        return self.root / str(assessment_id)

    async def save(self, assessment: FallRiskAssessment) -> None:
        async with self._lock:
            directory = self.directory(assessment.assessment_id)
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / "assessment.json"
            temporary = directory / "assessment.json.tmp"
            temporary.write_text(assessment.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(destination)

    async def get(self, assessment_id: UUID) -> FallRiskAssessment:
        path = self.directory(assessment_id) / "assessment.json"
        if not path.is_file():
            raise AssessmentNotFoundError(str(assessment_id))
        return FallRiskAssessment.model_validate_json(path.read_text(encoding="utf-8"))

    async def list(self, limit: int = 20) -> list[FallRiskAssessment]:
        paths = sorted(
            self.root.glob("*/assessment.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:limit]
        return [
            FallRiskAssessment.model_validate_json(path.read_text(encoding="utf-8"))
            for path in paths
        ]
