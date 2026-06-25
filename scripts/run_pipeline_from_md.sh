#!/usr/bin/env bash
set -euo pipefail

# Run Cullary's full pipeline sequentially for folders listed in a Markdown file.
#
# Supported Markdown forms:
#   /Users/liubin/Pictures/SetA
#   - /Users/liubin/Pictures/SetB
#   1. /Users/liubin/Pictures/SetC
#   `/Users/liubin/Pictures/SetD`
# Lines starting with # are ignored. Only absolute paths are extracted.
#
# Usage:
#   scripts/run_pipeline_from_md.sh paths.md
#   FORCE=0 scripts/run_pipeline_from_md.sh paths.md
#   VERIFY=1 scripts/run_pipeline_from_md.sh paths.md

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/hippo/bin/python}"
PYTHONPATH_VALUE="${PYTHONPATH:-src}"
FORCE="${FORCE:-1}"
VERIFY="${VERIFY:-0}"
PROGRESS="${PROGRESS:-jsonl}"
STOP_ON_ERROR="${STOP_ON_ERROR:-1}"
MD_FILE="${1:-}"

if [[ -z "$MD_FILE" ]]; then
  echo "Usage: $0 /path/to/folders.md" >&2
  exit 2
fi

if [[ ! -f "$MD_FILE" ]]; then
  echo "Markdown file not found: $MD_FILE" >&2
  exit 2
fi

mapfile -t PHOTO_DIRS < <(
  "$PYTHON_BIN" - "$MD_FILE" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
seen: set[str] = set()
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^\d+[.)]\s+", "", line)
    line = line.strip().strip("`").strip()
    match = re.search(r"(/[^`'\"<>]+)", line)
    if not match:
        continue
    value = match.group(1).strip()
    # Drop common trailing punctuation from prose lines.
    value = value.rstrip("，,。.;；")
    if value not in seen:
        seen.add(value)
        print(value)
PY
)

if [[ "${#PHOTO_DIRS[@]}" -eq 0 ]]; then
  echo "No absolute folder paths found in: $MD_FILE" >&2
  exit 2
fi

echo "Cullary batch pipeline"
echo "Markdown: $MD_FILE"
echo "Folders: ${#PHOTO_DIRS[@]}"
echo "Python: $PYTHON_BIN"
echo "Force: $FORCE"
echo "Verify: $VERIFY"
echo

FAILED=0
for index in "${!PHOTO_DIRS[@]}"; do
  folder="${PHOTO_DIRS[$index]}"
  number=$((index + 1))
  echo "===== [$number/${#PHOTO_DIRS[@]}] $folder ====="
  if [[ ! -d "$folder" ]]; then
    echo "SKIP: folder not found: $folder" >&2
    FAILED=$((FAILED + 1))
    if [[ "$STOP_ON_ERROR" == "1" ]]; then exit 1; fi
    continue
  fi

  args=("$folder" "--progress" "$PROGRESS")
  if [[ "$FORCE" == "1" ]]; then
    args+=("--force")
  fi

  if ! PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON_BIN" -m cullary.pipeline "${args[@]}"; then
    echo "FAILED: pipeline error for $folder" >&2
    FAILED=$((FAILED + 1))
    if [[ "$STOP_ON_ERROR" == "1" ]]; then exit 1; fi
    continue
  fi

  if [[ "$VERIFY" == "1" ]]; then
    "$PYTHON_BIN" scripts/verify_phase1_outputs.py "$folder"
    "$PYTHON_BIN" scripts/verify_phase2_outputs.py "$folder"
  fi
  echo
done

if [[ "$FAILED" -gt 0 ]]; then
  echo "Completed with failures: $FAILED" >&2
  exit 1
fi

echo "Completed all folders successfully."
