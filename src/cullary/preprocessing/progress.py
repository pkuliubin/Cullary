from __future__ import annotations

import json
import sys
from typing import Any


class ProgressReporter:
    def __init__(self, mode: str = "text") -> None:
        self.mode = mode

    def __call__(self, event: dict[str, Any]) -> None:
        if self.mode == "quiet":
            return
        if self.mode == "jsonl":
            print(json.dumps(event, ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)
            return
        line = self.format_text(event)
        if line:
            print(line, file=sys.stderr, flush=True)

    def format_text(self, event: dict[str, Any]) -> str | None:
        event_type = event.get("type")
        if event_type == "task_start":
            return f"[cullary] start folder={event.get('folder')} cache={event.get('cache_dir')}"
        if event_type == "scan_done":
            return f"[cullary] scan {event.get('total', 0)} photos ignored={event.get('ignored', {})}"
        if event_type == "stage_start":
            return f"[cullary] {event.get('stage')} start total={event.get('total', 0)}"
        if event_type == "stage_progress":
            return (
                f"[cullary] {event.get('stage')} "
                f"{event.get('done', 0)}/{event.get('total', 0)} "
                f"skipped={event.get('skipped', 0)} failed={event.get('failed', 0)}"
            )
        if event_type == "stage_done":
            return (
                f"[cullary] {event.get('stage')} done "
                f"skipped={event.get('skipped', 0)} failed={event.get('failed', 0)} "
                f"duration_ms={event.get('duration_ms', 0)}"
            )
        if event_type == "task_done":
            return (
                f"[cullary] done status={event.get('status')} "
                f"photos={event.get('total_photos', 0)} duration_ms={event.get('duration_ms', 0)}"
            )
        return None
