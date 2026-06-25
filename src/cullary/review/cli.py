from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cullary.constants import DEFAULT_CONFIG, DEFAULT_INPUT
from cullary.preprocessing.progress import ProgressReporter
from cullary.review.generator import ReviewSetGenerator
from cullary.utils import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cullary Phase 2 review set generation")
    parser.add_argument("folder", nargs="?", default=str(DEFAULT_INPUT), help="Photo folder containing .cullary")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Config JSON")
    parser.add_argument("--progress", choices=["text", "jsonl", "quiet"], default="text")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate review sets even when inputs are unchanged")
    args = parser.parse_args(argv)
    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"Input folder does not exist or is not a directory: {folder}", file=sys.stderr)
        return 2
    progress_mode = "quiet" if args.quiet else args.progress
    generator = ReviewSetGenerator(folder, load_config(Path(args.config)), ProgressReporter(progress_mode), force=args.force)
    try:
        summary = generator.run()
    except Exception as exc:
        print(json.dumps({"type": "failed", "stage": "review_sets", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Review summary: {generator.review_summary_path}")
    print(f"Review sets: {generator.review_sets_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
