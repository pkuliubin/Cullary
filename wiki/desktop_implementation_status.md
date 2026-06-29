# Desktop Implementation Status

This document records the current Tauri/Rust/Frontend implementation state.

Last verified: 2026-06-25.

Packaging plan: [Desktop Packaging Plan](desktop_packaging_plan.md).

## Implemented

Desktop scaffold:

```text
package.json
index.html
app/src/App.tsx
app/src/main.tsx
app/src/repository.js
app/src/styles.css
app/src/reviewState.js
vite.config.ts
tsconfig.json
src-tauri/
```

Mock review artifact:

```text
app/mock/cullary-demo/.cullary/review_summary.json
app/mock/cullary-demo/.cullary/review_sets.jsonl
app/mock/mockReviewData.js
app/scripts/validate-mock-data.mjs
app/scripts/test-review-state.mjs
app/scripts/test-staging-contract.mjs
app/scripts/test-built-ui.mjs
```

Rust/Tauri command layer:

```text
start_pipeline
cancel_pipeline
load_review_summary
load_review_sets
append_decision
load_decisions
load_review_progress
save_review_progress
append_preference_event
dry_run_stage
execute_stage
undo_stage
```

Frontend prototype:

- Start screen.
- Processing progress dashboard with product-level stages, substep progress, and no raw JSON log in the main UI.
- Deck-first review screen.
- Single keeper pool and challenger/delete-candidate pool for Schema 1.1.
- Alternate keepers are challengers by default, not automatically kept.
- Focused duel compare mode.
- Linked zoom/pan toggle.
- Full grid fallback view.
- Global final staging screen with final state, this-run diff, no-op counts, and undo.
- Mock decisions and preference event flow.
- Testable review state module for deck/compare/decision flow.
- Processing screen consumes pipeline progress events.
- Processing screen stores the active Tauri task id and can cancel a running pipeline.
- Mock staging contract covers source + sidecar move planning.
- React/TypeScript frontend entrypoint.
- Built UI smoke test validates production assets contain core review flow markers.
- Decisions are persisted in `decisions.jsonl` and restored on reopen.
- Completed review sets are persisted in `review_progress.json`.
- Compare decisions append preference events for future user-preference learning.
- Tauri asset protocol is used for cached thumbnails/previews; base64 data URL loading is fallback only.

## Validation

Passing checks:

```bash
npm run check:mock
npm run build
npm run test:review-state
npm run test:staging-contract
npm run test:render
npm run check:desktop
```

Current result:

```text
mock review contract ok: 1 sets, 12 photos
review state flow ok
staging contract ok
vite build passes
built UI smoke ok
```

Tauri/Rust build check:

```bash
npm run tauri:build -- --debug --no-bundle
```

Current result:

```text
Finished dev profile
Built application at: src-tauri/target/debug/cullary-desktop
```

## Notes

- Rust owns file staging.
- Rust emits pipeline terminal events from process exit status, so UI does not rely on Python stdout to leave `running`.
- Python must not move, delete, or rename source files.
- React reads Phase 2 fields through Rust/Tauri commands and does not infer keeper pools or challenger queues.
- Current frontend can develop against mock artifacts before real Phase 2 outputs are ready.
- Tauri asset protocol dynamically allows the selected `.cullary` directory so cached preview/thumb paths render via `convertFileSrc`.
- Dry-run staging writes `.cullary/stage_plan.current.json` instead of repeatedly creating timestamped plan files.
- Python pipeline launches through `python -m cullary.pipeline --progress jsonl` with an absolute `PYTHONPATH` resolved by Rust.
