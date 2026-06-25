# Cullary Desktop App Current Design

Last updated: 2026-06-25.

This document records the current implemented desktop app behavior. It should be treated as the front-end/Rust integration reference for the current Tauri build.

## Product Shape

Cullary is a local-first desktop photo culling workbench:

```text
Select folder
  -> Run local analysis
  -> Review similar-photo groups
  -> Confirm keep/delete intent
  -> Apply safe staging into .to_delete/
```

The app is not a cloud service and does not use a local HTTP backend. The UI is React in a Tauri shell, Rust owns local OS/file operations, and Python owns analysis/recommendation.

## Current Stack

```text
React + Vite      UI and interaction state
Tauri + Rust      folder picker, process management, file-contract bridge, safe staging
Python            preprocessing, embeddings, quality analysis, review set generation
.cullary files    durable integration contract
```

## Processing Screen

The processing screen should be a progress dashboard, not a raw log viewer.

Current design:

- one centered progress panel;
- no raw JSON event log in the main UI;
- four product-level stages;
- each product-level stage shows completed substeps as `done/total`;
- the current product-level stage expands its substeps;
- each substep shows its own percentage;
- previous stages are inferred complete when later stages start, so progress never appears to go backward.

Product-level stages:

```text
查找照片
  - 扫描文件

准备预览
  - 读取拍摄信息
  - 生成预览
  - 生成缩略图
  - 计算指纹

分析画面
  - 检测人脸
  - 识别主体
  - 画面指标
  - 相似画面
  - 画质评分

整理 Review
  - 读取结果
  - 生成分组
```

Python progress events should include `type`, `stage`, `done`, `total`, and preferably `percent`. The frontend can compute `percent` from `done/total` when missing.

## Review Model

The current UI uses Schema 1.1 style cluster review:

- one primary keeper by default;
- alternate keepers are high-priority challengers, not automatically kept;
- each photo has one global user decision state within the session;
- the visible states are simplified to `保留` and `待删除`.

User-facing semantics:

```text
保留     photo stays in its original folder
待删除   photo will be moved to .to_delete/ during final confirmation
```

There is no separate `Move Aside` state in the main UX anymore. `待删除` already means safe staging candidate, not permanent deletion.

## Review Screen

Layout:

```text
Top bar
Left cluster list | Main review deck / compare / grid | Right inspector
```

Cluster list:

- sorted by photo count, descending;
- each row shows cover thumbnail and cluster photo count;
- rows should stay minimal to avoid dashboard noise.

Deck mode:

- keeper strip: current `保留` photos;
- large selected preview;
- challenger strip: current `待删除` photos;
- bottom action bar: `保留`, `待删除`, `进入对比`;
- clicking any keeper/challenger changes the main preview immediately.

Right inspector:

- group keep ratio, e.g. `3/12`;
- retained size / total source size;
- safe staging explanation;
- current photo reasons and weaknesses in Chinese;
- mark group complete toggle.

`标记本组完成` is a checklist marker only. It does not move files or lock decisions. It is persisted to `.cullary/review_progress.json` and is used to show review completeness before global final confirmation.

## Compare Mode

Compare is a focused mode inside the review screen, not a separate app page.

Behavior:

- compares active keeper vs active challenger;
- next/previous moves through the current challenger pool;
- photos use `object-fit: contain`; no cropping in compare;
- linked zoom/pan is on by default;
- zoom/pan state is preserved across next/previous challenger navigation for detail inspection;
- mouse wheel zoom sensitivity is intentionally low.

Layout rule:

- default side-by-side;
- very wide landscape pairs can use stacked layout;
- ordinary 4:3 photos stay side-by-side.

Actions:

```text
替换保留       challenger becomes keep; old keeper becomes delete candidate
两张都保留     challenger is added to keeper pool
保持待删除     challenger remains delete candidate and compare advances
```

Compare inspector shows:

- each side's score, preview dimensions, and source size;
- similarity and overall score delta;
- key score dimensions such as technical quality, IQA, composition, face quality, and group-relative score.

## Decision Persistence

The app restores previous review work when reopening a folder.

Read on opening Review:

```text
.cullary/review_summary.json
.cullary/review_sets.jsonl
.cullary/decisions.jsonl
.cullary/review_progress.json
```

Write during review:

```text
.cullary/decisions.jsonl          photo keep/delete decisions
.cullary/preference_events.jsonl  compare preference events for future learning
.cullary/review_progress.json     completed cluster checklist
```

Latest decision wins for each `display_id`.

## Safe Staging

Final confirmation is global for the selected folder, not per cluster.

Source files are never permanently deleted by the current app. They are moved into:

```text
<input_folder>/.to_delete/
```

Rust owns staging because it is a local file operation close to the UI confirmation step.

Current staging behavior is diff-based and bidirectional:

```text
should be 待删除 + still in original path  -> move into .to_delete/
should be 待删除 + already in .to_delete/  -> no-op
should be 保留   + still in original path  -> no-op
should be 保留   + already in .to_delete/  -> restore to original path
```

Sidecars such as `.xmp` / `.XMP` follow the source file when present.

The final confirmation page separates:

```text
最终状态
  保留 N 张，待删除 M 张

本次变更
  移入 .to_delete X 张，恢复保留 Y 张

无需移动
  已在 .to_delete A 张，已在原位 B 张
```

Dry-run staging writes a single stable plan file:

```text
.cullary/stage_plan.current.json
```

It should not create timestamped `stage_plan_*.json` files repeatedly.

Execution writes operation logs to:

```text
.cullary/file_operations.jsonl
```

Undo uses the operation batch id from that log.

## Image Loading

The UI renders cached artifacts, not source RAW/HEIC files.

```text
Grid / strips: .cullary/thumbs/*
Deck / compare: .cullary/previews/*
Source files: only used by Rust staging, never rendered directly
```

Tauri asset protocol should be the primary image path. The app dynamically allows the selected folder's `.cullary` directory so previews/thumbs load via `convertFileSrc` rather than base64 IPC. The `read_image_data_url` path is a debug fallback only.

## Current Validation

Use these checks for desktop changes:

```bash
npm run check:desktop
npm run tauri:build -- --debug --no-bundle
```

`check:desktop` runs mock contract checks, review-state tests, staging-contract tests, Vite build, and built UI smoke test.
