from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import PIPELINE_STAGES, SCHEMA_VERSION
from .utils import now_iso, write_json


@dataclass
class StageRuntime:
    status: str = "pending"
    done: int = 0
    total: int = 0
    failed: int = 0
    skipped: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "failed": self.failed,
            "skipped": self.skipped,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


class TaskState:
    def __init__(self, task_id: str, folder: Path, cache_dir: Path, path: Path, total: int) -> None:
        self.task_id = task_id
        self.folder = folder
        self.cache_dir = cache_dir
        self.path = path
        self.started_at = now_iso()
        self.updated_at = self.started_at
        self.status = "running"
        self.current_stage = "scan"
        self.totals = {"discovered": total, "processable": total, "completed": 0, "failed": 0, "skipped": 0}
        self.stages = {stage: StageRuntime(total=total) for stage in PIPELINE_STAGES}
        self.errors: list[dict[str, Any]] = []

    def set_stage(self, stage: str, status: str) -> None:
        self.current_stage = stage
        runtime = self.stages[stage]
        runtime.status = status
        if status == "running" and runtime.started_at is None:
            runtime.started_at = now_iso()

    def finish_stage(self, stage: str) -> None:
        runtime = self.stages[stage]
        runtime.finished_at = now_iso()
        runtime.status = "partial_success" if runtime.failed else "success"
        if runtime.started_at:
            runtime.duration_ms = max(runtime.duration_ms, 1)

    def persist(self) -> None:
        self.updated_at = now_iso()
        write_json(self.path, self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "task_id": self.task_id,
            "folder": str(self.folder),
            "cache_dir": str(self.cache_dir),
            "status": self.status,
            "current_stage": self.current_stage,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "totals": self.totals,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "errors": self.errors[-50:],
        }
