#!/usr/bin/env bash
set -euo pipefail

# Generate and verify Phase 2 deck-first review outputs.
# Usage:
#   scripts/smoke_phase2.sh /path/to/photo-folder

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/hippo/bin/python}"
PHOTO_DIR="${1:-/Users/liubin/Desktop/TestImage}"
EVENT_LOG="${TMPDIR:-/tmp}/cullary-phase2-events.jsonl"

PYTHONPATH="${PYTHONPATH:-src}" "$PYTHON_BIN" -m cullary.review "$PHOTO_DIR" --quiet --force
"$PYTHON_BIN" scripts/verify_phase2_outputs.py "$PHOTO_DIR"

PYTHONPATH="${PYTHONPATH:-src}" "$PYTHON_BIN" -m cullary.pipeline "$PHOTO_DIR" --skip-preprocess --progress jsonl > "$EVENT_LOG"
python3 - "$EVENT_LOG" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
if not events:
    raise SystemExit('no pipeline events captured')
if events[-1].get('type') != 'completed':
    raise SystemExit(f'last event is not completed: {events[-1]}')
if not any(e.get('type') == 'progress' and e.get('stage') == 'review_sets' for e in events):
    raise SystemExit('missing review_sets progress event')
print(json.dumps({'status': 'success', 'event_count': len(events), 'last_event': events[-1]}, ensure_ascii=False, indent=2, sort_keys=True))
PY
