#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Cullary.app"
APP_PATH="$ROOT/src-tauri/target/release/bundle/macos/$APP_NAME"
DMG_DIR="$ROOT/src-tauri/target/release/bundle/dmg"
DMG_SCRIPT="$DMG_DIR/bundle_dmg.sh"
SOURCE_DIR="$DMG_DIR/internal-source"
OUTPUT="$DMG_DIR/Cullary_0.1.0_aarch64.dmg"

if [[ ! -d "$APP_PATH" ]]; then
  echo "missing release app: $APP_PATH" >&2
  echo "run: npm run runtime:build:release:app" >&2
  exit 1
fi
if [[ ! -x "$DMG_SCRIPT" ]]; then
  echo "missing Tauri DMG script: $DMG_SCRIPT" >&2
  exit 1
fi

rm -rf "$SOURCE_DIR" "$OUTPUT"
mkdir -p "$SOURCE_DIR"
ditto "$APP_PATH" "$SOURCE_DIR/$APP_NAME"

bash "$DMG_SCRIPT" \
  --skip-jenkins \
  --sandbox-safe \
  --volname "Cullary" \
  --app-drop-link 375 170 \
  "$OUTPUT" \
  "$SOURCE_DIR"

echo "$OUTPUT"
