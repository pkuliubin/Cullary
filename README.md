# Cullary

Cullary is a local-first photo culling tool that groups similar shots, recommends keepers and challengers, and safely stages non-keepers for review.

## Why

Camera workflows often produce many near-duplicate photos: burst shots, repeated portraits, bracketed scenes, and multiple attempts at the same composition. This is especially painful with large RAW files, NAS archives, and long-term photo libraries.

Cullary focuses on one job:

> Pick a folder, group similar photos, recommend keepers per similar-photo group, let the user confirm keep/delete intent, then safely move non-keepers aside for review.

## Product Principles

- Local-first: photos stay on the user's machine or NAS.
- Keep-first workflow: users confirm what to keep instead of manually selecting what to delete.
- Safe cleanup: non-keepers are moved to a staging folder, not permanently deleted.
- RAW-aware: large RAW files are preserved as the source of truth; previews or thumbnails are used for fast analysis.
- Offline batch processing: long processing time is acceptable if the results are reliable.

## Planned Workflow

1. Select a folder.
2. Scan photos and metadata.
3. Extract embedded previews or generate thumbnails.
4. Cluster near-duplicate photos using time, visual similarity, and optional GPS.
5. Recommend a primary keeper and useful challengers per cluster.
6. Review clusters in a task-focused desktop UI.
7. Apply a global final confirmation that moves non-keepers into `.to_delete/`, with undo support.

## Documentation

- [Related Products](wiki/related-products.md)
- [Implementation Plan](wiki/implementation-plan.md)
- [Road Map](wiki/road_map.md)
- [Preprocess Pipeline](wiki/preprocess.md)
- [Desktop App Current Design](wiki/desktop_app_current_design.md)
- [Desktop App Architecture](wiki/app_architecture.md)
- [Integration Contract](wiki/integration_contract.md)
- [Desktop Implementation Status](wiki/desktop_implementation_status.md)
- [Desktop Packaging Plan](wiki/desktop_packaging_plan.md)
- [Internal Test Guide](wiki/internal_test_guide.md)


## Desktop App

Run the desktop client in development:

```bash
npm install
npm run tauri:dev
```

Build a debug Tauri app without bundling:

```bash
npm run tauri:build -- --debug --no-bundle
```

Validate the current desktop contract:

```bash
npm run check:desktop
```

Verify the current bundled-runtime app path:

```bash
npm run runtime:verify
```

That command stages runtime resources, builds `Cullary Runtime.app`, runs an existing-artifact smoke test, and runs a 4-photo full-pipeline smoke test. The bundled runtime build stages only the required model whitelist from `packaging/models.manifest.json`; larger benchmark models under `~/.cullary/models` are not copied.

Individual runtime packaging steps are also available:

```bash
npm run runtime:stage
npm run runtime:build:app
npm run runtime:smoke
npm run runtime:smoke:full
```

Build an internal release DMG with bundled runtime:

```bash
npm run runtime:verify:release
```

Current internal DMG output:

```text
src-tauri/target/release/bundle/dmg/Cullary_0.1.0_aarch64.dmg
```

This internal DMG is unsigned and not notarized. It is suitable for local/internal testing, not a polished public release. `runtime:verify:release` also mounts the generated DMG and smoke-tests the app from `/Volumes/Cullary/`.

Current verification command:

```bash
npm run runtime:verify:release
```

Current result: passed on 2026-06-29.

Release summary output:

```text
src-tauri/target/release/bundle/Cullary Runtime.release-summary.json
```

The summary records the internal DMG path, size, SHA-256, and verification status.

The desktop app uses:

- React/Vite for UI;
- Tauri/Rust for folder access, Python process management, `.cullary` reads/writes, and safe file staging;
- Python for analysis and review-set generation;
- `.cullary/` artifacts as the local integration contract.

Pipeline launch is controlled by a runtime config. Development fallback is generated at `build/runtime.dev.json`; packaged builds will use `runtime.json` from the app resources. You can override it with:

```bash
CULLARY_RUNTIME_CONFIG=/path/to/runtime.local.json npm run tauri:dev
```

Runtime diagnostics are available through the Tauri command `get_runtime_diagnostics` for checking bundled Python, model, and exiftool paths. The start screen includes a Runtime Check button for internal testers to collect this information without opening developer tools.

Final confirmation is safe staging, not permanent deletion. Files marked `待删除` are moved to `<input_folder>/.to_delete/`; operation logs are written to `.cullary/file_operations.jsonl` and can be undone by batch.

## Phase 1 Preprocess Pipeline

Run the local preprocessing pipeline against a photo folder:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /Users/liubin/Desktop/TestImage
```

Progress is printed to stderr by default. For machine-readable logs or silent runs:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /Users/liubin/Desktop/TestImage --progress jsonl
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /Users/liubin/Desktop/TestImage --quiet
```

After installing the package locally, the formal console entry is:

```bash
/opt/anaconda3/envs/hippo/bin/python -m pip install -e .
cullary-preprocess /Users/liubin/Desktop/TestImage
```

The pipeline writes generated previews, thumbnails, per-photo analysis JSON, embedding vectors, `manifest.jsonl`, `task_state.json`, and `run_summary.json` under the selected folder's `.cullary/` directory. Source photos are read-only. Embedding uses Torch MPS automatically when available and falls back to CPU.

Verify the output contract:

```bash
/opt/anaconda3/envs/hippo/bin/python scripts/verify_phase1_outputs.py /Users/liubin/Desktop/TestImage
```

Run the full smoke check, including resume/stale behavior:

```bash
scripts/smoke_phase1.sh /Users/liubin/Desktop/TestImage
```

Run Phase 2 review-set generation and contract verification:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.review /Users/liubin/Desktop/TestImage
/opt/anaconda3/envs/hippo/bin/python scripts/verify_phase2_outputs.py /Users/liubin/Desktop/TestImage
```

Run the Tauri-facing full pipeline entry:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.pipeline /Users/liubin/Desktop/TestImage --progress jsonl
```

## Code Layout

- `src/cullary/preprocessing/`: Phase 1 pipeline orchestration, task state, manifest/run summary writes.
- `src/cullary/analyzers/`: reusable analyzer implementations for metadata/preview, hash, image metrics, embedding, face, and IQA.
- `scripts/`: smoke tests, verification helpers, benchmarks, and model download utilities.
