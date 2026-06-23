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

Purpose: build trust while the backend analyzes the folder.

Show the active pipeline stage and useful counts.

```text
┌──────────────────────────────────────────────┐
│ Processing /Users/.../Photos                 │
├──────────────────────────────────────────────┤
│ Scanning files              done             │
│ Extracting metadata         done             │
│ Building previews           312 / 580        │
│ Generating thumbnails       waiting          │
│ Analyzing quality           waiting          │
│ Grouping clusters           waiting          │
│ Recommending keepers        waiting          │
│                                              │
│ Failed: 2                                    │
│ Skipped: 7                                   │
└──────────────────────────────────────────────┘
```

The page should expose failures, but it should not interrupt the whole task unless the critical preview/cache layer fails.

## Screen 3: Cluster Review

This is the core product screen.

Recommended layout:

```text
┌────────────────────────────────────────────────────────────────────┐
│ Task: Winter trip     Remaining: 42 clusters      [Final Review]   │
├───────────────┬──────────────────────────────────┬─────────────────┤
│ Cluster list  │ Main workspace                   │ Recommendation  │
│               │                                  │                 │
│ [keeper] 12   │  Keeper slot 1                    │ 推荐保留：       │
│ [keeper] 8    │  Large keeper preview             │ - 人脸更清晰     │
│ [keeper] 21   │  Challengers: [B] [C] [D]          │ - 曝光更稳定     │
│ ...           │                                  │ - 与另一张有差异 │
│               │                                  │                 │
│               │  [View All Photos]                │ Top challengers │
├───────────────┴──────────────────────────────────┴─────────────────┤
│ [Accept Cluster] [Compare] [Keep More] [Undo] [Next]                │
└────────────────────────────────────────────────────────────────────┘
```

### Left Cluster List

Keep it minimal.

Each cluster row should show:

- recommended keeper thumbnail;
- number of photos in the cluster;
- confirmation status;
- optional warning marker only when needed.

Example:

```text
[thumb] 12 photos   未确认
[thumb]  8 photos   已确认
[thumb] 21 photos   低置信度
```

Avoid showing raw scores, camera metadata, timestamps, and multiple metrics in the list.

### Main Cluster Area

The main workspace should be deck-first, not grid-first.

Default mode is `deck`:

```text
keeper slots, 1-3 recommended keepers
  -> active keeper large preview
  -> top challenger strip
  -> Chinese recommendation reasons
```

The full cluster grid is a secondary mode, entered through `View All Photos`.

`View All Photos` should be visible in the deck, not hidden in an overflow menu. Deck-first should guide review, but it must not make the user feel that the system is hiding unshown photos.

The deck should show cluster coverage copy such as:

```text
本组 20 张，显示 2 个推荐保留和 5 个重点挑战者
[查看全部]
```

This preserves global awareness while keeping the primary flow focused.

Reason:

- the backend already recommends 1-3 keeper slots;
- each keeper slot has targeted challengers;
- most user work should be validating or correcting recommendations, not manually searching through every photo;
- full grid remains available for low-confidence or unusual clusters.

Default behavior:

- system-recommended keepers are visually prominent;
- recommended rejects are subdued, but not styled as deleted;
- user can override every suggestion;
- the system recommends 1-3 keepers per cluster;
- the 1-3 keepers should be diversity-aware, not three near-identical frames.

Review modes inside the cluster screen:

```ts
type ReviewMode = "deck" | "compare" | "grid"
```

Mode behavior:

```text
deck     primary review deck, keeper slots plus top challengers
compare  focused two-image detail compare inside the same cluster screen
grid     secondary full-cluster thumbnail view
```

### Keeper Slots

If the system recommends more than one keeper, the deck should show all keeper slots clearly.

Recommended structure:

```text
Keeper slots: [Keeper 1] [Keeper 2] [Keeper 3]

Active keeper:
  large preview
  recommendation reasons
  challenger queue
```

The user can switch active keeper slots. Switching keeper slots updates the large preview, reasons, and challenger queue.

This matters because Cullary should preserve useful diversity. Three recommendations that look nearly identical are not helpful; multiple keeper slots should communicate distinct value, such as:

```text
Keeper 1: 最清晰的人像
Keeper 2: 表情不同
Keeper 3: 构图更完整
```

Suggested visual states:

```text
recommended_keep     strong outline / accent label
user_keep            confirmed keep state
recommended_reject   lower opacity, still recoverable
user_reject          marked for move-aside, still undoable
staged_to_delete     only after final staging operation
```

Do not use permanent-delete language during cluster review.

Use language like:

```text
保留
标记移出
待清理
撤销
```

Avoid language like:

```text
删除
永久删除
```

until the final file operation confirmation.

### Recommendation Inspector

Recommendation reasons should be shown in Chinese.

Good form:

```text
推荐保留这张：
- 人脸更清晰
- 眼睛状态正常
- 曝光更稳定
- 和另一张推荐图有构图差异
```

For non-keepers:

```text
不优先推荐：
- 面部略虚
- 高光溢出较多
- 和已推荐照片过于相似
```

Scores can exist as secondary details, but the primary UI should be human-readable reasons.

## Keeper Recommendation Model in UI

For each cluster, the backend should provide:

```text
recommended_keepers: 1-3 photos
```

Each keeper should also have targeted challengers:

```text
Keeper 1
  challenger queue: B, C, D

Keeper 2
  challenger queue: E, F

Keeper 3
  challenger queue: G
```

This makes compare mode focused. The user should not need to manually compare every possible pair in a 20-photo cluster.

The challenger queue is ordered. The first item should be the most likely alternative to the current keeper, not a random remaining photo.

Queue quality is part of the product experience. A good challenger queue should prioritize:

- photos that are visually similar enough to replace the keeper;
- photos with close or better technical quality;
- meaningful expression, pose, or composition alternatives;
- diversity candidates that might deserve `Keep Both`.

The first few challengers should not be obvious failures unless the reason is to explain why they were rejected.

## Compare Mode

Compare is a first-class MVP feature.

Purpose: inspect details such as sharpness, eyes, expression, focus, and small exposure differences.

Compare is not a separate app-level page and should not be implemented as a heavy modal overlay. It is a focused mode inside Cluster Review.

State model:

```ts
type ReviewState = {
  mode: "deck" | "compare" | "grid"
  currentClusterId: string
  activeKeeperSlotId: string
  activeKeeperPhotoId: string
  activeChallengerPhotoId?: string
}
```

Entering compare changes only:

```text
mode = "compare"
```

The current cluster, keeper slot, and challenger context remain stable. Returning from compare restores `mode = "deck"` and keeps the same selected keeper/challenger context.

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
Replace            challenger replaces current keeper slot
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

Cluster review only records user decisions. It should not move files immediately.

After all clusters are confirmed, show a final staging screen.

Purpose: safely move user-confirmed rejects into `_to_delete/`.

```text
┌──────────────────────────────────────────────┐
│ Final Review                                 │
├──────────────────────────────────────────────┤
│ Keep: 184                                    │
│ Move aside: 396                              │
│ Destination: /Photos/_to_delete/             │
│ Sidecars: include matching XMP if present    │
│ Log: .cullary_cache/file_operations.jsonl    │
│                                              │
│ No files will be permanently deleted.         │
│                                              │
│ [Back to Review]       [Move to _to_delete]  │
└──────────────────────────────────────────────┘
```

Why this step exists:

- cluster review marks decisions;
- final staging performs file operations;
- user can still review the total impact;
- operation logs make undo/recovery possible;
- sidecar movement can be checked consistently.

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
  -> inspect recommended keepers
  -> compare keeper with challenger queue when needed
  -> accept or adjust decisions
  -> confirm cluster
  -> move to next cluster
```

The UI should make the next decision obvious. A user should not need to understand the whole analysis pipeline to finish one cluster.

### Selection Behavior

Recommended behavior in the cluster grid:

```text
single click photo         select photo and show reasons
double click challenger    open compare against current keeper
checkbox/action button     mark keep / mark move-aside
Compare button             enter compare with selected challenger queue
View All Photos            switch to full cluster grid mode
Accept Cluster             apply current keep/move-aside decisions and confirm cluster
Undo                       revert last decision in current cluster
```

This avoids overloading a single click with destructive meaning.

### Keyboard Support

The review page should be fully usable by keyboard.

Suggested shortcuts:

```text
J / K or ↓ / ↑     previous / next cluster
← / →              previous / next photo in current cluster
C                  open compare
A                  accept cluster
K                  mark selected as keep
R                  mark selected as move-aside
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

Each cluster recommendation should expose:

```json
{
  "cluster_id": "...",
  "recommended_keepers": [
    {
      "photo_id": "...",
      "rank": 1,
      "confidence": 0.86,
      "reason_summary_zh": [
        "人脸更清晰",
        "眼睛状态正常",
        "曝光更稳定"
      ],
      "diversity_reason_zh": "和第一张推荐图构图不同",
      "challenger_queue": [
        {
          "photo_id": "...",
          "rank": 1,
          "reason_zh": "清晰度接近，但表情略弱"
        }
      ]
    }
  ],
  "recommended_rejects": [
    {
      "photo_id": "...",
      "reason_summary_zh": ["面部略虚", "和推荐照片过于相似"]
    }
  ]
}
```

### Required Decision Fields

User decisions should be separate from system recommendations.

```json
{
  "cluster_id": "...",
  "photo_id": "...",
  "system_recommendation": "reject",
  "user_decision": "keep",
  "decision_source": "manual_override",
  "created_at": "..."
}
```

Recommended state separation:

```text
recommended_reject  # system suggestion
user_marked_reject  # user confirmed mark
staged_to_delete    # file has been moved to _to_delete
```

These states must not be collapsed.

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
real file moving
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
- compare mode can move previous/next through a keeper's challenger queue;
- linked zoom/pan can be toggled on and off;
- user decisions are visually distinct from system recommendations;
- `Accept Cluster` changes only review state, not source files;
- every primary action is reachable by mouse and keyboard;
- recommendation reasons are readable in Chinese;
- final staging screen clearly says files are moved aside, not permanently deleted.
