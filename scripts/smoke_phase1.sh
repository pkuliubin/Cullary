#!/usr/bin/env bash
set -euo pipefail

# Run the Phase 1 pipeline and verify its output contract.
# Usage:
#   scripts/smoke_phase1.sh /path/to/photo-folder

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/envs/hippo/bin/python}"
PHOTO_DIR="${1:-/Users/liubin/Desktop/TestImage}"

PYTHONPATH="${PYTHONPATH:-src}" "$PYTHON_BIN" -m cullary.preprocessing "$PHOTO_DIR"
"$PYTHON_BIN" scripts/verify_phase1_outputs.py "$PHOTO_DIR"

# Contract-level resume/stale test on a generated temp folder.
"$PYTHON_BIN" scripts/test_phase1_resume.py
