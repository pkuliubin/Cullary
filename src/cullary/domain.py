from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AnalyzerStatus:
    status: str
    version: str
    config_hash: str
    duration_ms: int
    started_at: str
    finished_at: str
    error_message: str | None = None
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "version": self.version,
            "config_hash": self.config_hash,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
            "output_path": self.output_path,
        }


@dataclass
class PhotoRecord:
    source_id: str
    display_id: str
    source_path: Path
    relative_path: str
    file_name: str
    extension: str
    size: int
    mtime_ns: int
    analysis_dir: Path
    analysis_path: Path
    preview_path: Path
    thumb_path: Path
    embedding_path: Path
    metadata_raw_path: Path
    source_changed: bool = False
    analysis: dict[str, Any] = field(default_factory=dict)
    changed_stages: set[str] = field(default_factory=set)
