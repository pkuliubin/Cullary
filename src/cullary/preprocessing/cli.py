from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cullary.constants import DEFAULT_CONFIG, DEFAULT_INPUT
from cullary.preprocessing.pipeline import PreprocessPipeline
from cullary.preprocessing.progress import ProgressReporter
from cullary.utils import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cullary Phase 1 local preprocessing pipeline")
    parser.add_argument("folder", nargs="?", default=str(DEFAULT_INPUT), help="Photo folder to scan")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Preprocess config JSON")
    parser.add_argument("--force", action="store_true", help="Re-run all analyzers")
    parser.add_argument("--limit", type=int, help="Process only the first N photos; useful for smoke tests")
    parser.add_argument("--progress", choices=["text", "jsonl", "quiet"], default="text", help="Progress output format on stderr")
    parser.add_argument("--quiet", action="store_true", help="Alias for --progress quiet")
    args = parser.parse_args(argv)

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"Input folder does not exist or is not a directory: {folder}", file=sys.stderr)
        return 2
    progress_mode = "quiet" if args.quiet else args.progress
    pipeline = PreprocessPipeline(folder, load_config(Path(args.config)), force=args.force, limit=args.limit, progress=ProgressReporter(progress_mode))
    summary = pipeline.run()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Manifest: {pipeline.manifest_path}")
    print(f"Task state: {pipeline.task_state_path}")
    print(f"Summary: {pipeline.summary_path}")
    return 0 if summary.get("status") in {"success", "partial_success"} else 1
