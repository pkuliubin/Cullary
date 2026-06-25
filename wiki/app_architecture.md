# Cullary Desktop App Architecture

This document defines the current frontend/backend architecture direction for Cullary.

Cullary is a local-first desktop client. It may use web UI technology, but it is not a web app and does not require a cloud backend or a persistent local HTTP API for the current product track.

## Architecture Thesis

Use Tauri's native Rust layer as a thin local app layer, not as a second business backend.

```text
React UI
  -> Tauri commands/events
  -> thin Rust app layer
  -> Python pipeline
  -> .cullary file contract
```

Responsibilities should stay separated:

```text
React  = interaction and presentation
Rust   = OS integration, process management, file-contract bridge
Python = analysis, clustering, recommendation
Files  = durable local integration contract
```

## Why This Shape

Cullary needs desktop capabilities:

- choose local/NAS folders;
- run long local analysis jobs;
- read/write local cache artifacts;
- render many cached thumbnails/previews;
- move files safely into `.to_delete/`;
- keep all originals local and private.

Tauri is a natural fit because it gives us:

- a WebView UI for fast React iteration;
- an official Rust backend layer for local system access;
- command/event IPC between UI and native layer;
- process management for Python workers.

However, Rust should remain thin at this stage. The image-analysis domain logic already belongs in Python and should not be duplicated in Rust.

## Non-Goals for Current Track

Do not introduce these unless a concrete later need appears:

- cloud backend;
- persistent local HTTP API server;
- Redis;
- mandatory SQLite task/review DB;
- Rust reimplementation of image analysis or recommendation;
- React directly invoking Python scripts everywhere;
- React directly scattering file reads/writes across the codebase.

SQLite can be introduced later behind the same repository interface. The `.cullary` file contract should remain stable enough to migrate from.

## High-Level Components

```text
┌─────────────────────────────────────────────────────────┐
│ React / TypeScript UI                                   │
│ - Start / Processing / Review / Compare / Staging       │
│ - deck-first review interaction                         │
│ - local UI state, review progress, compare controls     │
└───────────────────────┬─────────────────────────────────┘
                        │ Tauri commands + events
┌───────────────────────▼─────────────────────────────────┐
│ Thin Rust App Layer                                      │
│ - folder picker / path validation                        │
│ - spawn and supervise Python pipeline                    │
│ - parse progress events                                  │
│ - read/write .cullary contract files                     │
│ - emit progress/status to UI                             │
│ - call staging dry-run / execute commands                │
└───────────────────────┬─────────────────────────────────┘
                        │ process spawn / stdout events
┌───────────────────────▼─────────────────────────────────┐
│ Python Pipeline                                          │
│ - Phase 1 preprocessing                                  │
│ - Phase 2 review set generation                          │
│ - future preference learning                             │
└───────────────────────┬─────────────────────────────────┘
                        │ durable artifacts
┌───────────────────────▼─────────────────────────────────┐
│ .cullary/ File Contract                                  │
│ - manifest.jsonl                                         │
│ - previews/                                              │
│ - thumbs/                                                │
│ - analysis/                                              │
│ - embeddings/                                            │
│ - review_sets.jsonl                                      │
│ - review_summary.json                                    │
│ - decisions.jsonl                                        │
│ - preference_events.jsonl                                │
│ - file_operations.jsonl                                  │
│ - review_progress.json                                   │
│ - stage_plan.current.json                                │
└─────────────────────────────────────────────────────────┘
```

## Data Ownership

### Python Owns Generated Review Model

Python owns files produced by analysis/recommendation phases:

```text
manifest.jsonl
analysis/
embeddings/
previews/
thumbs/
review_sets.jsonl
review_summary.json
review_debug.json
```

Phase 2 output is the review model. Frontend should not recalculate keeper pools, challenger queues, scores, or recommendations.

Rust reads and validates these generated artifacts for the UI, but it should not generate or mutate Phase 1 / Phase 2 outputs.

### UI Owns Ephemeral Interaction State

React owns transient state such as:

```text
current review set
active keeper
active challenger
review mode: deck | compare | grid
linked zoom state
local undo stack
selected photo
```

This state may be persisted later, but it does not belong in Phase 2 output.

### Decision Files Own User Decisions

User-confirmed choices should be written separately from Phase 2 recommendations:

```text
.cullary/decisions.jsonl
.cullary/preference_events.jsonl
```

System recommendations and user decisions must remain separate.

Recommended writer ownership:

```text
Python writes generated artifacts:
  manifest.jsonl
  analysis/
  embeddings/
  previews/
  thumbs/
  review_sets.jsonl
  review_summary.json

Rust appends UI/user artifacts:
  decisions.jsonl
  preference_events.jsonl
  review_progress.json

Rust owns file staging:
  dry-run staging plan
  execute safe staging operations
  undo staging operations
  file_operations.jsonl
```

Python must not move, delete, or rename source files. It only produces recommendations and review models.

## Thin Rust Layer Responsibilities

Rust should expose stable commands to React.

Suggested commands:

```ts
chooseFolder(): Promise<string>

startPipeline(folder: string): Promise<{ taskId: string }>
cancelPipeline(taskId: string): Promise<void>

loadReviewSummary(folder: string): Promise<ReviewSummary>
loadReviewSets(folder: string): Promise<ReviewSet[]>

appendDecision(folder: string, decision: DecisionEvent): Promise<void>
appendPreferenceEvent(folder: string, event: PreferenceEvent): Promise<void>

dryRunStage(folder: string): Promise<StagePlan>
executeStage(folder: string): Promise<StageResult>
undoStage(folder: string, operationBatchId: string): Promise<UndoResult>
```

Suggested events:

```ts
pipeline-progress
pipeline-completed
pipeline-failed
pipeline-cancelled
```

Rust should not expose the entire filesystem to React. It should validate paths and centralize file contract reads/writes.

## Python Pipeline Interface

Rust starts Python commands and reads structured stdout events.

Tauri-facing command:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.pipeline /path/to/folder --progress jsonl
```

Phase-specific commands such as `cullary.preprocessing` and `cullary.review` may exist for development, but Rust/Tauri production integration should depend on the single `cullary.pipeline` module entry.

Example pipeline event:

```json
{"type":"progress","stage":"preview","done":120,"total":580,"message":"Building previews"}
```

Completion event:

```json
{"type":"completed","summary_path":".cullary/review_summary.json","review_sets_path":".cullary/review_sets.jsonl"}
```

Failure event:

```json
{"type":"failed","stage":"embedding","error":"model unavailable"}
```

Python should write durable artifacts to `.cullary/`; Rust should validate and expose them to UI.

Python pipeline phases must never perform final source file operations. Source file movement is owned by Rust staging commands.

## Rust-Owned File Staging

File staging is the final user-confirmed operation that moves user-marked non-keepers into `.to_delete/`.

It is owned by Rust/Tauri because it is a local client file operation close to the UI confirmation step.

Staging flow:

```text
React calls dryRunStage(folder)
  -> Rust reads decisions.jsonl and review_sets.jsonl
  -> Rust builds a stable StagePlan at .cullary/stage_plan.current.json
  -> UI shows final state, this-run changes, no-op counts, and conflicts

React calls executeStage(folder, planId)
  -> Rust applies a diff-based bidirectional staging plan
  -> Rust moves non-keepers into .to_delete/
  -> Rust restores newly kept files from .to_delete/ when needed
  -> Rust writes file_operations.jsonl
  -> UI shows final state and this-run changes

React calls undoStage(folder, operationBatchId)
  -> Rust reads file_operations.jsonl
  -> Rust moves files back where possible
```

Rust staging must handle:

- source file existence checks;
- `.to_delete/` destination planning;
- relative path preservation when needed;
- sidecar detection and movement;
- name conflicts without overwriting;
- partial failure reporting;
- operation batch IDs;
- undo logs.

## Frontend Data Access Pattern

The React app should use a repository layer instead of importing raw file access everywhere.

```ts
interface CullaryReviewRepository {
  loadSummary(folder: string): Promise<ReviewSummary>
  loadReviewSets(folder: string): Promise<ReviewSet[]>
  appendDecision(folder: string, decision: DecisionEvent): Promise<void>
  appendPreferenceEvent(folder: string, event: PreferenceEvent): Promise<void>
}
```

First implementation:

```text
TauriFileReviewRepository -> Tauri commands -> .cullary files
```

Future implementation:

```text
SqliteReviewRepository -> Tauri commands -> SQLite
```

The UI should not care which storage backend is used.

## UI Data Flow

```text
User chooses folder
  -> React calls chooseFolder()
  -> React calls startPipeline(folder)
  -> Rust spawns Python pipeline
  -> Python writes .cullary artifacts and emits progress
  -> Rust forwards progress to React
  -> React loads review_summary + review_sets after completion
  -> User reviews deck-first sets and focused compare queues
  -> React writes decisions through Rust command
  -> Final staging calls dryRunStage / executeStage
```

## File Contract First, DB Later

Current track should continue using `.cullary` files.

Reasons:

- Phase 1 and Phase 2 already produce file artifacts;
- debugging is easy;
- schemas are still evolving;
- large binary artifacts belong in files anyway;
- later SQLite migration can import from these artifacts.

To keep migration easy:

- keep schema versions in every output file;
- use stable IDs (`display_id`, `source_id`, `review_set_id`, `slot_id`);
- keep recommendation output separate from user decisions;
- keep generated artifacts separate from operation logs;
- centralize reads/writes behind Rust commands and frontend repository interfaces.

## Current Recommended Stack

```text
Desktop shell: Tauri
UI: React + TypeScript
Native bridge: thin Rust command/event layer
Analysis/recommendation: Python
Durable data: .cullary file contract
Future optional DB: SQLite behind same repository boundary
```

## Architecture Guardrails

- Do not make React parse arbitrary analyzer internals.
- Do not make React infer keeper pools or challenger queues.
- Do not move source files during Phase 1 or Phase 2.
- Do not move source files from Python pipeline code.
- Do not treat system recommendation as user deletion decision.
- Do not use preview images in large grids; use thumbs.
- Do not introduce HTTP API, Redis, or SQLite before there is a clear need.
- Do not duplicate scoring/recommendation logic in Rust.

## Open Decisions

These can be decided later without blocking current work:

- when to introduce SQLite as a read model;
- how to package Python runtime/models inside the Tauri app.

已冻结的集成决策：Tauri-facing Python pipeline 使用 stdout JSONL progress events；非 JSON 日志输出到 stderr。
