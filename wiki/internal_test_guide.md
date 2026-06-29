# Cullary Internal Test Guide

This guide is for internal macOS testers using the unsigned Cullary build.

## Package

Current internal package:

```text
src-tauri/target/release/bundle/dmg/Cullary_0.1.0_aarch64.dmg
src-tauri/target/release/bundle/Cullary.release-summary.json
```

The app is unsigned and not notarized. It is for internal testing only.

## Install

1. Open the DMG.
2. Drag `Cullary.app` to `Applications`.
3. Open it from Finder.

If macOS blocks the app because it is unsigned:

1. Right-click `Cullary.app`.
2. Choose `Open`.
3. Confirm `Open` again.

If the app is still blocked during internal testing, run:

```bash
xattr -dr com.apple.quarantine "/Applications/Cullary.app"
```

## First Run Check

Before analyzing a folder:

1. Open Cullary.
2. Click `运行环境检查` on the start screen.
3. Confirm Python, model dir, ExifTool, and config are all green.

If any item is red, send a screenshot of the check panel.

## Test Flow

Use a small copied photo folder first, not an original archive.

1. Choose a folder with 20-100 photos.
2. Click `开始分析`.
3. Wait for processing to finish.
4. Review a few groups.
5. Use `全局最终确认` only on test copies.

Cullary moves non-keepers into `.to_delete/`; it should not permanently delete files.

## What To Report

If something fails, send:

- macOS version and Mac chip type.
- Whether the app was run from `/Applications` or directly from the DMG.
- Screenshot of `运行环境检查`.
- Screenshot of the error screen.
- The selected folder path.
- The folder's `.cullary/run_summary.json` if it exists.
- The folder's `.cullary/review_summary.json` if it exists.
- The release summary JSON file.

## Build Verification For Developers

Before sharing a package, run:

```bash
npm run runtime:verify:release
```

This stages the runtime, builds the release app, creates the internal DMG, smoke-tests the release app, mounts the DMG, smoke-tests the app from `/Volumes/Cullary/`, and writes the release summary.
