from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from cullary.constants import DEFAULT_CONFIG, DEFAULT_INPUT
from cullary.preprocessing.pipeline import PreprocessPipeline
from cullary.review.generator import ReviewSetGenerator
from cullary.utils import cache_relative, load_config


class PipelineEventReporter:
    def __init__(self, mode: str, event_stream: Any | None = None) -> None:
        self.mode = mode
        self.event_stream = event_stream or sys.stdout

    def __call__(self, event: dict[str, Any]) -> None:
        if self.mode == "quiet":
            return
        mapped = self.map_event(event)
        if not mapped:
            return
        if self.mode == "jsonl":
            print(json.dumps(mapped, ensure_ascii=False, sort_keys=True), file=self.event_stream, flush=True)
        else:
            print(f"[cullary] {mapped.get('stage', mapped.get('type'))} {mapped.get('done', '')}/{mapped.get('total', '')} {mapped.get('message', '')}".strip(), file=sys.stderr, flush=True)

    def map_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = event.get("type")
        if event_type == "stage_progress":
            done = int(event.get("done", 0) or 0)
            total = int(event.get("total", 0) or 0)
            percent = round((done / total) * 100) if total else 0
            return {
                "type": "progress",
                "stage": event.get("stage"),
                "done": done,
                "total": total,
                "percent": percent,
                "message": f"Running {event.get('stage')}",
            }
        if event_type == "stage_done":
            return {
                "type": "progress",
                "stage": event.get("stage"),
                "done": event.get("total", 0) or 0,
                "total": event.get("total", 0) or 0,
                "percent": 100,
                "message": f"Finished {event.get('stage')}",
            }
        if event_type == "scan_done":
            total = int(event.get("total", 0) or 0)
            return {"type": "progress", "stage": "scan", "done": total, "total": total, "percent": 100, "message": "Scan complete"}
        if event_type == "progress":
            done = int(event.get("done", 0) or 0)
            total = int(event.get("total", 0) or 0)
            event["percent"] = round((done / total) * 100) if total else event.get("percent", 0)
            return event
        return None


def emit(mode: str, event: dict[str, Any], event_stream: Any | None = None) -> None:
    if mode == "quiet":
        return
    if mode == "jsonl":
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), file=event_stream or sys.stdout, flush=True)
    else:
        print(f"[cullary] {event}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cullary full local pipeline: preprocess + review sets")
    parser.add_argument("folder", nargs="?", default=str(DEFAULT_INPUT), help="Photo folder to process")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Config JSON")
    parser.add_argument("--force", action="store_true", help="Re-run Phase 1 analyzers")
    parser.add_argument("--limit", type=int, help="Limit photos for development smoke tests")
    parser.add_argument("--skip-preprocess", action="store_true", help="Generate review sets from existing Phase 1 outputs")
    parser.add_argument("--progress", choices=["text", "jsonl", "quiet"], default="text")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        emit("jsonl" if args.progress == "jsonl" else "text", {"type": "failed", "stage": "start", "error": f"Input folder does not exist: {folder}"})
        return 2
    mode = "quiet" if args.quiet else args.progress
    config = load_config(Path(args.config))
    event_stream = sys.stdout
    reporter = PipelineEventReporter(mode, event_stream)
    stdout_guard = contextlib.redirect_stdout(sys.stderr) if mode == "jsonl" else contextlib.nullcontext()
    try:
        with stdout_guard:
            if not args.skip_preprocess:
                preprocess = PreprocessPipeline(folder, config, force=args.force, limit=args.limit, progress=reporter)
                preprocess_summary = preprocess.run()
                if preprocess_summary.get("status") not in {"success", "partial_success"}:
                    emit(mode, {"type": "failed", "stage": "preprocess", "error": preprocess_summary.get("status", "unknown")}, event_stream)
                    return 1
            review = ReviewSetGenerator(folder, config, reporter, force=args.force)
            review_summary = review.run()
            emit(mode, {
                "type": "completed",
                "summary_path": cache_relative(review.review_summary_path, folder),
                "review_sets_path": cache_relative(review.review_sets_path, folder),
            }, event_stream)
            if mode != "jsonl":
                print(json.dumps(review_summary, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        emit(mode, {"type": "failed", "stage": "pipeline", "error": f"{type(exc).__name__}: {exc}"}, event_stream)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
