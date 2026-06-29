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

Stage runtime resources for future app packaging:

```bash
python3 scripts/package_runtime.py
```

For a local smoke staging that also copies the current Python environment:

```bash
python3 scripts/package_runtime.py --output build/cullary-runtime-with-python --python-env /opt/anaconda3/envs/hippo
```

Build a debug `.app` that bundles that staged runtime:

```bash
npm run tauri:build -- --debug --bundles app --config src-tauri/tauri.bundle-runtime.conf.json
```

The desktop app uses:

- React/Vite for UI;
- Tauri/Rust for folder access, Python process management, `.cullary` reads/writes, and safe file staging;
- Python for analysis and review-set generation;
- `.cullary/` artifacts as the local integration contract.

Pipeline launch is controlled by a runtime config. Development fallback is generated at `build/runtime.dev.json`; packaged builds will use `runtime.json` from the app resources. You can override it with:

```bash
CULLARY_RUNTIME_CONFIG=/path/to/runtime.local.json npm run tauri:dev
```

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
