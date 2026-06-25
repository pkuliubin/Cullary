# Cullary Parallel Implementation Contract

This document defines the minimum contract needed for two agents to work in parallel:

- Python agent implements Phase 2 review set generation.
- Tauri/Rust/React agent implements the desktop client shell and review UI integration.

The goal is to avoid blocking on each other while keeping the integration boundary stable.

## Ownership Split

```text
Python owner:
  Phase 1/2 generated artifacts
  review_sets.jsonl
  review_summary.json
  progress JSON events

Rust/Tauri owner:
  process launch and cancellation
  reading/validating .cullary artifacts
  decisions/preference event append
  Rust-owned file staging
  UI-facing commands/events

React owner:
  review UI based on one cluster-level Keeper pool and Challenger pool
  compare mode
  local review state
  calls Tauri commands only
```

## Python CLI Contract

Freeze the Tauri-facing pipeline entry as a Python module command. Rust should call the full pipeline entry, not individual implementation scripts.

Tauri-facing full pipeline command:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.pipeline /path/to/folder --progress jsonl
```

Development/debug phase commands may also exist:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /path/to/folder --progress jsonl
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.review /path/to/folder --progress jsonl
```

Ownership rule:

- Rust/Tauri production integration calls `cullary.pipeline`.
- Python can internally call/reuse `cullary.preprocessing` and `cullary.review`.
- Frontend/Rust should not depend on script file paths such as `scripts/preprocess.py`.

Environment note:

- Current local dev Python is `/opt/anaconda3/envs/hippo/bin/python`.
- Packaging may replace this with a bundled runtime later, but the module interface should remain stable.

## Python Stdout Event Contract

Python should emit JSON Lines on stdout for progress. Non-JSON logs should go to stderr.

This is the frozen external event contract for Rust/Tauri. Python internals may use other event names, but `--progress jsonl` on the Tauri-facing command must emit these event types.

Progress event:

```json
{"type":"progress","stage":"preview","done":120,"total":580,"percent":21,"message":"Building previews"}
```

`percent` is recommended. If it is missing, the frontend computes it from `done / total`.

Completed event:

```json
{"type":"completed","summary_path":".cullary/review_summary.json","review_sets_path":".cullary/review_sets.jsonl"}
```

Failed event:

```json
{"type":"failed","stage":"review_sets","error":"embedding file missing"}
```

Compatibility note:

- Existing Phase 1 internals may emit `stage_progress`.
- The integration boundary should normalize this to `progress` before Rust depends on it.

Recommended stages:

```text
scan
metadata
preview
thumb
hash
image_metrics
embedding
face
iqa
review_load
review_sets
completed
```

Rust should tolerate unknown stages and display the `message` field when present.

## Required Phase 2 Artifacts

After Python completes successfully, these files must exist:

```text
<input_folder>/.cullary/review_summary.json
<input_folder>/.cullary/review_sets.jsonl
```

Every `review_sets.jsonl` row must include the cluster-level review fields defined in `wiki/phase_2_plan.md`:

```text
schema_version
review_set_id
set_type
photo_count
cover_display_id
primary_keeper_id
recommended_keep_ids[]          # schema 1.1: only the primary keeper by default
alternate_keeper_ids[]          # good candidates, not default keepers
alternate_keeper_count
challenger_queue[]              # cluster-level queue, every non-primary photo
challenger_queue[].photo_id
challenger_queue[].compare_to   # primary_keeper_id
keeper_slots[]                  # compatibility only; not the primary UI model
photos[]
photos[].display_id
photos[].source_path
photos[].thumb_path
photos[].thumb_width
photos[].thumb_height
photos[].preview_path
photos[].preview_width
photos[].preview_height
photos[].recommendation
photos[].ui_initial_state
photos[].reason_summary_zh[]
photos[].weakness_summary_zh[]
reason_summary_zh[]
```

`review_summary.json` should include at least:

```text
schema_version
status
folder
cache_dir
input_manifest_path
review_sets_path
total_photos
review_set_count
single_count
near_duplicate_count
similar_scene_count
recommended_keep_count
alternate_keeper_count
keeper_slot_count
challenger_count
lower_ranked_count
duration_ms
config_hash
input_hash
cache_hit
failures[]
```

Rust/React should not infer the recommendation model. React should prefer `primary_keeper_id`, `alternate_keeper_ids`, and the cluster-level `challenger_queue`; `keeper_slots[]` is kept only as a short-term compatibility field.

Rust-owned file staging requires `photos[].source_path`. React should not render source files, but Rust needs the path to build dry-run and execute safe staging operations.

## Mock Artifact Contract

Frontend/Rust development may start before real Phase 2 is complete by using mock artifacts with the same schema.

Preferred mock paths inside a test folder:

```text
<input_folder>/.cullary/review_summary.json
<input_folder>/.cullary/review_sets.jsonl
```

The mock should use real existing `thumb_path` and `preview_path` values when possible so the UI can validate image loading, aspect ratios, review deck, and compare mode.

Mock data must satisfy the same required field list as real Phase 2 output. No frontend-only mock schema is allowed.

## Path Contract

Python may write relative paths inside `.cullary` artifacts.

Rust should resolve relative artifact paths against the input folder root:

```text
input folder: /Photos/Trip
thumb_path: .cullary/thumbs/A.jpg
resolved: /Photos/Trip/.cullary/thumbs/A.jpg
```

Python should not emit paths outside the selected input folder except for source file paths already discovered during scan.

## Decision Event Contract

Rust appends user decision events to:

```text
<input_folder>/.cullary/decisions.jsonl
```

Minimum event:

```json
{
  "schema_version": "1.0",
  "event_id": "...",
  "event_type": "photo_decision",
  "review_set_id": "set_000001",
  "display_id": "B0007796_HEIC",
  "previous_user_state": "user_undecided",
  "user_state": "user_keep",
  "source": "manual",
  "created_at": "2026-06-24T12:00:00Z"
}
```

Allowed `user_state` values for the first implementation:

```text
user_keep
user_challenger   # UI label: 待删除; final confirmation moves it to .to_delete/
user_undecided
```

## Preference Event Contract

Rust appends compare/review preference events to:

```text
<input_folder>/.cullary/preference_events.jsonl
```

Minimum compare event:

```json
{
  "schema_version": "1.0",
  "event_id": "...",
  "event_type": "compare_decision",
  "review_set_id": "set_000001",
  "active_keeper_photo_id": "A",
  "challenger_photo_id": "B",
  "user_action": "replace_with_challenger",
  "linked_view_used": true,
  "created_at": "2026-06-24T12:00:00Z"
}
```

Allowed first-pass `user_action` values:

```text
keep_current
replace_with_challenger
keep_both
skip_challenger
```

## Rust/Tauri Command Contract

Initial commands:

```ts
chooseFolder(): Promise<string>
startPipeline(folder: string): Promise<{ taskId: string }>
cancelPipeline(taskId: string): Promise<void>
loadReviewSummary(folder: string): Promise<ReviewSummary>
loadReviewSets(folder: string): Promise<ReviewSet[]>
appendDecision(folder: string, decision: DecisionEvent): Promise<void>
appendPreferenceEvent(folder: string, event: PreferenceEvent): Promise<void>
dryRunStage(folder: string): Promise<StagePlan>
executeStage(folder: string, planId: string): Promise<StageResult>
undoStage(folder: string, operationBatchId: string): Promise<UndoResult>
```

Initial events:

```text
pipeline-progress
pipeline-completed
pipeline-failed
pipeline-cancelled
```

## Rust-Owned File Staging Contract

Python must not move, delete, or rename source files.

Rust owns final staging:

```text
dryRunStage
executeStage
undoStage
file_operations.jsonl
```

`dryRunStage` reads decisions and review sets, then returns a plan without moving files.

`executeStage` applies a diff-based staging plan. It moves photos whose latest decision is `user_challenger` into `.to_delete/`, restores photos whose latest decision is `user_keep` from `.to_delete/` when necessary, and writes an operation batch to:

```text
<input_folder>/.cullary/file_operations.jsonl
```

## Parallel Work Guidance

Python agent can proceed if it satisfies:

- Phase 2 schema in `wiki/phase_2_plan.md`;
- stdout event contract in this document;
- no source file operations.

Tauri/Rust/React agent can proceed by using:

- mock `review_summary.json` and `review_sets.jsonl` matching Phase 2 schema;
- Tauri command stubs for pipeline launch;
- real file reads for generated artifacts once Python is ready;
- Rust-owned decisions/preference/staging files.

## Integration Test Checklist

Before merging the two sides:

- Rust can launch Python and receive JSON progress events.
- Python completion produces `review_summary.json` and `review_sets.jsonl`.
- Rust can load and validate all required Phase 2 fields.
- React can render review sets without additional recommendation inference.
- React reads `primary_keeper_id`, `alternate_keeper_ids`, and cluster-level `challenger_queue` as the primary model.
- Compare mode advances through the global Challenger pool, not per-slot queues.
- Decisions append to `decisions.jsonl`.
- Preference events append to `preference_events.jsonl`.
- Dry-run staging does not move files and writes/refreshes `.cullary/stage_plan.current.json`.
- Execute staging writes `file_operations.jsonl`.
- Reopening Review restores latest decisions from `decisions.jsonl` and completed sets from `review_progress.json`.
