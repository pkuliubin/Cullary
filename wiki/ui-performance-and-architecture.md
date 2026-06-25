# UI Performance Experiment and Architecture Notes

This document records the first local UI performance experiment and the resulting UI/backend requirements for Cullary.

## Goal

Validate whether a Tauri/WebView-style desktop UI is suitable for rendering large photo review grids.

The main question was not whether source RAW/HEIC files can be decoded in the UI. Cullary should never render source files directly. The real UI question is:

```text
Can the desktop UI smoothly render a large grid of cached analysis images?
```

## Experiment Setup

Two benchmark helpers were added:

- `scripts/benchmark_preview_io.py`
- `scripts/generate_ui_benchmark.py`

The UI benchmark generates a static HTML page that loads cached images from local `file://` URLs. It includes two modes:

- `Full render`: mounts every image node at once.
- `Virtual render`: mounts only images near the current viewport.

The benchmark reports:

- total image count;
- mounted image count;
- render time;
- decoded image count;
- decode p95 time.

The test used existing cached previews under:

```text
.cullary_cache/previews/
```

The benchmark repeated 46 source preview files 25 times, producing a 1150-image test set.

## Results

### Preview-as-grid Test

First test: use existing preview images directly in the grid.

Generated page:

```text
docs/ui-image-benchmark.html
```

Observed result from browser screenshot:

```text
images: 1150
mounted: 117
render ms: 1
decode p95 ms: 2309
```

Interpretation:

- Virtual rendering worked: only 117 image nodes were mounted.
- DOM rendering itself was cheap.
- Decode cost was too high because grid cells were loading large preview images.

### Thumbnail Grid Test

Second test: generate 360px long-edge thumbnails from the same previews, then render those in the grid.

Command:

```bash
python3 scripts/generate_ui_benchmark.py .cullary_cache/previews \
  --repeat 25 \
  --thumb-dir .cullary_cache/thumbs_360 \
  --thumb-edge 360 \
  --output docs/ui-image-benchmark-thumbs.html
```

Generated page:

```text
docs/ui-image-benchmark-thumbs.html
```

Observed result from browser screenshot:

```text
images: 1150
mounted: 117
render ms: 23
decode p95 ms: 74
```

Interpretation:

- Virtual rendering still worked.
- Decode p95 dropped from about 2309ms to about 74ms.
- The main UI risk is not local file IO. It is image decode size and mounted image count.

## Conclusion

Tauri/WebView is suitable for Cullary's desktop UI if the UI follows strict image-loading rules.

The correct architecture is:

```text
source original
  -> cached medium preview
  -> cached thumbnail
  -> UI grid/review
```

The UI must not behave like this:

```text
source RAW/HEIC/JPEG
  -> directly rendered in grid
```

And it should also avoid this:

```text
preview_1600
  -> directly rendered in large grid/list
```

## UI Architecture Requirements

### Image Tiers

Cullary should maintain separate image tiers:

```text
source original
  - .3FR / HEIC / JPG original file
  - used only for final keep/move operations
  - never rendered directly in normal UI grids

preview_1600 or preview_2400
  - medium JPEG preview
  - used for cluster review, compare mode, and large single-image display

thumb_360
  - small JPEG/WebP thumbnail
  - used for cluster lists, grids, filmstrips, and overview screens

optional tiny_80
  - optional future tier
  - used for very dense timelines or task summaries
```

### Grid and List Rendering

All grid/list UI must use thumbnails, not previews.

Required behavior:

- Use virtualized rendering for large grids and cluster lists.
- Mount only viewport-near image nodes.
- Use `thumb_path` for grid cells.
- Load `preview_path` only after entering cluster review or compare mode.
- Never send image bytes through IPC as base64.
- Pass paths/metadata only; let the WebView load cached image files directly.

### Review Screen

The cluster review screen can load medium previews because it displays far fewer images at once.

Expected behavior:

- Filmstrip uses `thumb_path`.
- Main compare panes use `preview_path`.
- Source original path is used only for metadata, final file operations, or future full-resolution inspection.

## Backend Requirements

The preprocessing/backend pipeline should produce UI-ready image assets, not only analysis previews.

### Cache Layout

Current cache layout has previews:

```text
.cullary_cache/
  previews/
    <source_id>.jpg
```

Recommended layout:

```text
.cullary_cache/
  previews/
    <source_id>.jpg       # medium preview, e.g. long edge 1600 or 2400
  thumbs/
    <source_id>.jpg       # grid thumbnail, e.g. long edge 360
  analysis/
    <source_id>/
      analysis.json
      metadata.json
      hash.json
      quality.json
      iqa.json
  manifest.jsonl
  run_summary.json
```

### Manifest Fields

Each manifest record should include both preview and thumbnail paths.

Recommended fields:

```json
{
  "source_id": "...",
  "source": {
    "path": "...",
    "extension": ".heic",
    "size": 123,
    "mtime_ns": 123
  },
  "preview_path": ".../.cullary_cache/previews/<source_id>.jpg",
  "preview_width": 1600,
  "preview_height": 1200,
  "thumb_path": ".../.cullary_cache/thumbs/<source_id>.jpg",
  "thumb_width": 360,
  "thumb_height": 270
}
```

The exact dimensions can vary by aspect ratio. The important contract is that the UI can choose the correct asset without inspecting or decoding source files.

### Analyzer Contract

Thumbnail generation should be treated as part of the preview/cache layer, not as a UI concern.

Recommended analyzer/cache outputs:

```text
preview extractor
  - generates preview_path
  - records preview dimensions
  - records extraction method

thumbnail generator
  - consumes preview_path
  - generates thumb_path
  - records thumb dimensions
```

If thumbnail generation fails but preview extraction succeeds, the record should expose that failure explicitly. The UI can fall back to preview for tiny sample sets, but this should be treated as degraded mode.

### Performance Requirements

Initial practical targets:

- Grid cells should use thumbnails around 320-480px long edge.
- Medium previews should be around 1600-2400px long edge.
- The UI should not mount more than a few hundred image nodes at once.
- Large task views should be virtualized from the first implementation.
- Backend should generate thumbnails during preprocessing, before UI review starts.

## Product Implication

The experiment supports using Tauri + React/TypeScript for the desktop UI.

However, the UI implementation must be built around cached image tiers and virtualization from day one. If the UI directly uses medium previews or source files in grids, performance will degrade even if Tauri itself is not the bottleneck.
