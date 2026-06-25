# Cullary UI Design

This document defines the first UI direction for Cullary: design principles, main screens, review workflow, compare mode, and backend requirements.

Cullary should not feel like a general photo gallery. It should feel like a focused local culling workbench: open a folder, let the system group and recommend, then make safe human decisions cluster by cluster.

## Product UI Thesis

Cullary is a quiet photo decision desk.

The UI should keep chrome low and make the photo comparison task dominant. AI recommendations should be visible and explainable, but never feel like automatic deletion. The user remains the final decision maker.

Core principles:

- Task-first, not gallery-first.
- Cluster-first, not file-list-first.
- Human-confirmed decisions, not automatic deletion.
- Image-led UI with minimal chrome.
- Recommendations in Chinese, explained like a review assistant.
- Performance by design: grid uses thumbnails, review uses medium previews, source files are never rendered directly.

## MVP Workflow

The MVP should use a sequential workflow:

```text
Start task
  -> Process folder
  -> Review clusters
  -> Final staging
```

Important decision:

- Review starts after processing is complete.
- The MVP does not support reviewing while analysis is still running.
- The MVP does not batch-accept low-risk clusters automatically.
- Every cluster requires user confirmation.

## Screen 1: Start Task

Purpose: start one local culling job.

The screen should be simple and utilitarian.

```text
┌──────────────────────────────────────────────┐
│ Cullary                                      │
│ Local photo culling taskbench                │
│                                              │
│ Folder: /path/to/photos                      │
│ [Choose Folder]                              │
│                                              │
│ Formats: JPG / JPEG / HEIC / 3FR             │
│ Pipeline: metadata -> previews -> analysis   │
│           -> clusters -> recommendations     │
│                                              │
│                         [Start Analysis]     │
└──────────────────────────────────────────────┘
```

Do not add dashboard cards, global albums, statistics panels, or marketing-style hero copy.

## Screen 2: Processing

Purpose: show trustworthy progress while the backend analyzes the folder.

The processing screen should not expose raw JSON logs in the main UI. It should present a product-level progress dashboard.

Current model:

```text
查找照片      shows completed substeps / total substeps
准备预览      shows completed substeps / total substeps
分析画面      shows completed substeps / total substeps
整理 Review   shows completed substeps / total substeps

Current product step expands its substeps:
  检测人脸 100%
  识别主体 68%
  画面指标 0%
```

Rules:

- product-level steps show substep completion count, not raw per-photo percent;
- substeps show their own percentage;
- previous stages should never visually go backward;
- when later stages start, earlier stages can be inferred complete;
- raw logs may exist for debugging, but should not dominate the product UI.

The page should expose failure state and a recovery path such as `使用已有结果`, but it should not interrupt the whole task unless critical artifacts are missing.

## Screen 3: Cluster Review

This is the core product screen.

Current layout:

```text
Top bar
├─ left: cluster list
├─ center: deck / compare / grid workspace
└─ right: group summary, current photo reasons, decision status
```

### Left Cluster List

Keep it minimal. Sort clusters by photo count descending so the highest-impact groups are reviewed first.

Each cluster row should show:

- cover thumbnail;
- number of photos in the cluster;
- confirmation status when useful.

Avoid raw scores, camera metadata, timestamps, and dense metrics in the list.

### Deck Mode

Deck mode is the default review mode. It uses a simple two-pool mental model:

```text
保留      photos that will stay in the original folder
待删除    photos that will move to .to_delete/ during final confirmation
```

The backend provides `primary_keeper_id`, `alternate_keeper_ids`, and a cluster-level `challenger_queue`. The UI initializes only the primary keeper as `保留`. Alternates are shown as higher-priority challengers, not automatically kept.

Deck layout:

```text
保留 strip
large selected preview
待删除 strip
bottom actions: 保留 / 待删除 / 进入对比
```

Clicking any keeper or challenger immediately changes the main preview.

### Right Inspector

The right inspector should be compact and decision-oriented:

- keep ratio, e.g. `3/12`;
- retained source size / total source size;
- safe staging explanation;
- mark group complete checklist;
- current photo recommendation reasons and weaknesses in Chinese.

`标记本组完成` is only a checklist marker. It does not move files, lock decisions, or delete anything.

### Language

Use user-safe language:

```text
保留
待删除
安全暂存区
应用最终确认
撤销
```

Avoid implying automatic or permanent deletion during cluster review.

## Compare Mode

Compare is a first-class MVP feature.

Purpose: inspect details such as sharpness, eyes, expression, focus, and small exposure differences.

Compare is not a separate app-level page and should not be implemented as a heavy modal overlay. It is a focused mode inside Cluster Review.

State model:

```ts
type ReviewState = {
  mode: "deck" | "compare" | "grid"
  currentClusterId: string
  activeKeeperPhotoId: string
  activeChallengerPhotoId?: string
}
```

Entering compare changes only:

```text
mode = "compare"
```

The current cluster, keeper, and challenger context remain stable. Returning from compare restores `mode = "deck"` and keeps the same selected keeper/challenger context.

### Entry Points

Compare mode can be opened from:

- recommended keeper vs top challenger;
- selected photo vs current keeper;
- two manually selected photos.

### Focused Duel with Challenger Queue

Compare should show one pair at a time, but support continuous challenger browsing.

Recommended model:

```text
active keeper: A
challenger queue: B, C, D, E

current duel:
A vs B
```

The user can move through the queue:

```text
A vs B
Next Challenger
A vs C
Next Challenger
A vs D
```

This is more efficient than repeatedly entering and exiting compare, while still preserving the detail quality of a two-image comparison.

Avoid multi-image compare in the MVP. Showing one keeper against many challengers at once makes each image too small, complicates linked zoom/pan, and makes the decision semantics unclear.

Core actions:

```text
Keep Current       keep the current keeper and continue
Replace            challenger becomes keep; old keeper returns to delete candidates
Keep Both          both photos become keepers
Previous/Next      move through challenger queue
Back to Cluster    return to deck mode
```

If `Replace` is selected, the MVP may either:

- update the current keeper and continue through remaining challengers; or
- update the current keeper and return to deck mode.

The simpler first implementation is to update and return to deck mode.

### Compare Layout

Use orientation-aware layout by default.

```text
landscape + landscape -> stacked top/bottom
portrait + portrait   -> side by side
square or mixed        -> side by side
```

Reason:

- landscape images become too small when placed left/right;
- portrait images become too short when placed top/bottom.

User should still be able to override:

```text
Auto / Side by side / Stacked
```

### Compare Wireframes

Landscape pair:

```text
┌───────────────┬────────────────────────────────────────┬──────────────┐
│ Cluster list  │ Compare: A vs B    Linked: On          │ Compare info │
│               │ [Prev] [Next] [Unlock] [Reset]         │              │
│               ├────────────────────────────────────────┤ A 推荐保留   │
│               │                Image A                 │ B 挑战者     │
│               ├────────────────────────────────────────┤              │
│               │                Image B                 │ [Keep A]     │
│               │                                        │ [Replace]    │
│               │                                        │ [Keep Both]  │
│               │                                        │ [Back]       │
└───────────────┴────────────────────────────────────────┴──────────────┘
```

Portrait pair:

```text
┌───────────────┬────────────────────────────────────────┬──────────────┐
│ Cluster list  │ Compare: A vs B    Linked: On          │ Compare info │
│               │ [Prev] [Next] [Unlock] [Reset]         │              │
│               ├────────────────────┬───────────────────┤ A 推荐保留   │
│               │      Image A        │      Image B      │ B 挑战者     │
│               │                     │                   │              │
│               │                     │                   │ [Keep A]     │
│               │                     │                   │ [Replace]    │
│               │                     │                   │ [Keep Both]  │
│               │                     │                   │ [Back]       │
└───────────────┴────────────────────┴───────────────────┴──────────────┘
```

### Linked Zoom and Pan

Compare mode should support linked zoom/pan.

Default:

```text
Linked: On
```

Behavior:

- zooming image A zooms image B;
- panning image A pans image B;
- zooming or panning either image updates the other;
- double-click reset resets both.

When unlinked:

```text
Linked: Off
```

Behavior:

- each image can be zoomed and panned independently;
- reset affects the active image;
- optional `Sync views` copies the active view to the other image.

Implementation should synchronize normalized image viewport, not raw pixel translation.

Recommended state shape:

```ts
type NormalizedView = {
  scale: number
  centerX: number // 0-1 relative to image width
  centerY: number // 0-1 relative to image height
}
```

This works better than copying pixel offsets because two images can have different dimensions or pane sizes.

## Screen 4: Final Staging

Cluster review records user intent. It should not move files immediately.

Final staging is global for the selected folder. It applies the latest decisions across all clusters.

Current behavior:

```text
保留     stays in original location
待删除   moves to <input_folder>/.to_delete/
```

No files are permanently deleted in the current app.

The final confirmation screen should separate final state from this-run diff:

```text
最终状态
  保留 78 张，待删除 35 张

本次变更
  移入 .to_delete 0 张，恢复保留 1 张

无需移动
  已在 .to_delete 35 张，已在原位 77 张
```

This avoids misleading copy such as `移动 35 张` when those 35 photos are already staged.

The Rust layer owns staging and writes operation logs to `.cullary/file_operations.jsonl`. Undo is performed by operation batch id.

## Visual Direction

Cullary should feel like a professional review bench, not an AI SaaS dashboard.

Recommended style:

- dark neutral workspace;
- photos are the brightest elements;
- low-chrome panels;
- thin separators instead of heavy cards;
- one accent color for recommendation/active state;
- calm typography;
- warning colors only for final destructive-risk moments.

Suggested accent:

```text
warm yellow-green or soft amber
```

Use red sparingly. Red should mean actual danger or final file operation risk, not merely system-recommended rejection.

### Refined Design System

The UI should use a dark, image-first workspace, but avoid generic purple SaaS styling. The visual system should be closer to a quiet editing bench than a dashboard.

Recommended tokens:

```text
background          near-black warm neutral
surface             dark graphite
surface_elevated    slightly lighter graphite
text_primary         warm off-white
text_secondary       muted warm gray
divider             low-contrast olive/graphite line
accent              yellow-green or soft amber
danger              reserved red, only for final destructive-risk actions
```

Accent usage:

- active cluster;
- recommended keeper outline;
- linked compare mode indicator;
- primary action.

Avoid:

- purple/cyan AI-dashboard gradients;
- glowing decorative panels;
- red for ordinary reject recommendations;
- metric-heavy cards;
- emoji as icons.

Typography should be calm and dense. Use a legible UI sans for labels and controls, with tabular numbers for counters and progress. Body text should not go below 13px on desktop; important actions and recommendation reasons should remain readable at a glance.

## Motion and Interaction

Motion should support orientation and confidence, not decoration.

Recommended small motions:

- smooth transition from cluster grid to compare mode;
- subtle highlight when a keeper is accepted;
- quick undo feedback when a decision changes;
- linked zoom/pan should feel physically synchronized.

Avoid ornamental dashboard animations.

Recommended timing:

```text
micro feedback       120-180ms
panel transition     180-260ms
compare transition   220-320ms
```

All motion should be interruptible and should respect reduced-motion settings.

## Interaction Refinements

### Primary Review Loop

The default loop should be:

```text
open cluster
  -> inspect current keeper pool and delete candidates
  -> compare keeper with challenger queue when needed
  -> mark photos 保留 / 待删除
  -> mark cluster complete as a checklist item
  -> move to next cluster
```

The UI should make the next decision obvious. A user should not need to understand the whole analysis pipeline to finish one cluster.

### Selection Behavior

Recommended behavior in the cluster grid:

```text
single click photo         select photo and show reasons
保留 button                mark selected photo as keep
待删除 button              mark selected photo as delete candidate
Compare button             enter compare with selected challenger queue
View All Photos            switch to full cluster grid mode
标记本组完成               checklist marker only; no file movement
Undo                       revert last decision when available
```

This avoids overloading a single click with destructive meaning.

### Keyboard Support

The review page should be fully usable by keyboard.

Suggested shortcuts:

```text
J / K or ↓ / ↑     previous / next cluster
← / →              previous / next photo in current cluster
C                  open compare
K                  mark selected as keep
D                  mark selected as 待删除
L                  toggle linked zoom in compare
0                  reset zoom
Esc                exit compare
Cmd/Ctrl+Z         undo
In compare:
← / →              previous / next challenger
Enter              keep current and continue
B                  keep both
R                  replace keeper with challenger
```

Shortcuts should be discoverable from a small help overlay, not memorized from documentation.

### Accessibility Requirements

Required from the first implementation:

- visible focus ring for all interactive elements;
- all icon buttons have accessible labels;
- recommendation state is not conveyed by color alone;
- image tiles have meaningful alt text from filename or capture metadata;
- tab order follows visual order;
- compare mode has an escape route via `Esc` and visible Back button;
- no keyboard trap inside zoom/pan mode.

### Image Grid Requirements

The grid must reserve image space before load to avoid layout shift.

Required:

```text
thumb_width / thumb_height known before render
CSS aspect-ratio set from metadata
loading="lazy" for offscreen images
virtualized rendering for cluster lists and grids
```

Do not rely on image load to determine layout.

## Backend Requirements

The UI needs structured task, cluster, recommendation, and decision data. A flat file list is not enough.

### Required Photo Fields

Each photo should expose:

```json
{
  "photo_id": "...",
  "source_path": "...",
  "thumb_path": "...",
  "thumb_width": 360,
  "thumb_height": 270,
  "preview_path": "...",
  "preview_width": 1600,
  "preview_height": 1200,
  "capture_time": "...",
  "metadata": {
    "camera_model": "...",
    "lens_model": "...",
    "focal_length": 35,
    "exposure_time": "1/250",
    "aperture": 2.8,
    "iso": 400
  }
}
```

### Required Cluster Fields

Each cluster should expose:

```json
{
  "cluster_id": "...",
  "session_id": "...",
  "photo_ids": ["..."],
  "photo_count": 12,
  "representative_photo_id": "...",
  "status": "unconfirmed",
  "warnings": ["low_confidence"]
}
```

### Required Recommendation Fields

Current Schema 1.1 review model:

```json
{
  "review_set_id": "set_000001",
  "photo_count": 12,
  "primary_keeper_id": "A",
  "recommended_keep_ids": ["A"],
  "alternate_keeper_ids": ["B"],
  "challenger_queue": [
    {
      "photo_id": "B",
      "compare_to": "A",
      "rank": 1,
      "similarity_to_primary": 0.94,
      "score_delta": -0.06,
      "reason_zh": "视觉相似度较高，可作为对比候选"
    }
  ],
  "photos": [
    {
      "display_id": "A",
      "source_path": "/path/to/A.3FR",
      "thumb_path": ".cullary/thumbs/A.jpg",
      "preview_path": ".cullary/previews/A.jpg",
      "ui_initial_state": "recommended_keep",
      "score": { "overall": 0.78 },
      "reason_summary_zh": ["技术质量较好"],
      "weakness_summary_zh": []
    }
  ]
}
```

UI rule: only `primary_keeper_id` / `recommended_keep_ids[0]` starts as `保留`. `alternate_keeper_ids` are challengers with a visual alternate marker.

### Required Decision Fields

User decisions are separate from system recommendations and are appended to `decisions.jsonl`. Latest decision wins.

```json
{
  "schema_version": "1.0",
  "event_type": "photo_decision",
  "review_set_id": "set_000001",
  "display_id": "A",
  "previous_user_state": "user_challenger",
  "user_state": "user_keep",
  "source": "manual",
  "created_at": 1782360000000
}
```

Current user states:

```text
user_keep        UI label: 保留
user_challenger  UI label: 待删除; final staging candidate
```

### Preference Learning Log

Cullary should record review and compare decisions for future user preference learning.

The MVP does not need to train a preference model, but it should preserve the data.

Recommended log event:

```json
{
  "event_type": "compare_decision",
  "cluster_id": "...",
  "keeper_photo_id": "...",
  "challenger_photo_id": "...",
  "user_action": "keep_challenger",
  "linked_view_used": true,
  "features_snapshot": {
    "embedding_version": "...",
    "quality_metrics": {},
    "face_metrics": {},
    "iqa_score": 0.73,
    "metadata": {}
  },
  "created_at": "..."
}
```

Future use:

- learn preferred exposure style;
- learn portrait vs landscape priorities;
- learn how often the user overrides sharpness/aesthetic recommendations;
- adapt keeper ranking over time.

## Performance Requirements

The UI performance experiment showed that thumbnails are mandatory for large grids.

Required image usage:

```text
grid/list/filmstrip -> thumb_360
main review image   -> preview_1600 or preview_2400
source original     -> never rendered directly in normal UI
```

Required rendering behavior:

- virtualize large lists and grids;
- do not send image bytes through IPC;
- pass file paths and metadata only;
- WebView loads local cached image assets directly;
- do not use medium previews as grid thumbnails.

## MVP Scope Summary

MVP UI should include:

- start task screen;
- processing screen;
- cluster review screen;
- compare mode with focused duel plus challenger queue;
- compare mode with orientation-aware layout;
- linked zoom/pan with on/off toggle;
- Chinese recommendation reasons;
- final staging screen;
- decision logging for future preference learning.

MVP UI should not include:

- full catalog management;
- album browsing;
- cloud sync;
- automatic deletion;
- batch acceptance of low-risk clusters;
- editing tools;
- Lightroom-style timeline as the primary surface.

## Frontend Implementation Readiness

The frontend can start with a static-data prototype before the backend schema is finalized.

Recommended first prototype scope:

```text
1. app shell with four screens
2. cluster review layout
3. deck-first review mode with optional full grid
4. recommendation inspector with Chinese reason text
5. compare mode with auto layout and challenger queue
6. linked zoom/pan toggle
7. virtualized thumbnail grid
8. local decision state and undo
```

Use mock JSON that follows the backend requirement examples in this document. The prototype should make it easy to swap mock data for backend data later.

Do not implement in the first frontend pass:

```text
permanent delete
real preference learning model
batch accept
photo editing
global album browsing
advanced filters
```

### Frontend Acceptance Checklist

Before considering the first UI prototype usable:

- 1000+ thumbnails can scroll smoothly in virtualized mode;
- no grid uses `preview_path` where `thumb_path` is available;
- compare mode supports both landscape stacked layout and portrait side-by-side layout;
- compare mode can move previous/next through the current challenger pool;
- linked zoom/pan can be toggled on and off;
- user decisions are visually distinct from system recommendations;
- `标记本组完成` changes only checklist progress, not source files;
- every primary action is reachable by mouse and keyboard;
- recommendation reasons are readable in Chinese;
- final staging screen clearly says files are moved aside, not permanently deleted.
