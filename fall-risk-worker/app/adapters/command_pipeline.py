from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


class PipelineExecutionError(RuntimeError):
    """Safe pipeline failure without command arguments or private paths."""


@dataclass(frozen=True, slots=True)
class CommandPipeline:
    name: str
    python: str
    runner: Path
    project_root: Path

    @property
    def configured(self) -> bool:
        return Path(self.python).is_file() and self.runner.is_file() and self.project_root.is_dir()

    async def run(self, arguments: list[str]) -> None:
        if not self.configured:
            raise PipelineExecutionError(f"{self.name} pipeline is not configured")
        process = await asyncio.create_subprocess_exec(
            self.python,
            str(self.runner),
            *arguments,
            cwd=self.project_root,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return_code = await process.wait()
        if return_code != 0:
            raise PipelineExecutionError(self.failure_message(return_code))

    def failure_message(self, return_code: int) -> str:
        if return_code == 20:
            return f"{self.name} did not detect a usable full-body walking sequence"
        return f"{self.name} pipeline failed"
