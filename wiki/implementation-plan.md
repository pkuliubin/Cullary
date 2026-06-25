# Cullary Implementation Plan

Cullary is a local-first photo culling taskbench. The core job is to scan a folder, group similar photos, recommend keepers, and let the user safely move non-keepers aside.

## MVP Scope

**Input**

- A folder path.
- Recursive scan.
- Initial formats: `.jpg`, `.jpeg`, `.heic`, `.3fr`.

**Output**

- A local scan database/cache.
- Cluster results.
- Recommended keepers per cluster.
- A review UI.
- A `.to_delete/` staging folder for rejected photos.

**Non-goals for MVP**

- Full photo catalog management.
- Cloud sync.
- RAW editing.
- Permanent deletion by default.
- VLM-based semantic reasoning.

## Core Workflow

```text
Select folder
  -> scan files
  -> read metadata
  -> extract preview/thumbnail
  -> compute image features
  -> split sessions by time
  -> cluster visually similar photos within each session
  -> score photos inside each cluster
  -> recommend primary keepers and challengers
  -> user confirms or edits keepers
  -> move non-keepers to staging
```

## Metadata and Preview Extraction

Cullary should separate the source file from the analysis image. The source file is the original photo that will be kept or moved; the analysis image is a cached JPEG preview/thumbnail used for clustering, IQA, face detection, and UI display.

### RAW / Hasselblad `.3FR`

For RAW files, especially Hasselblad `.3FR`, do not decode full RAW data unless needed.

Preferred strategy:

1. Try direct ExifTool extraction tags: `PreviewImage`, `JpgFromRaw`, `ThumbnailImage`.
2. If direct extraction is empty, read IFD0 tags with ExifTool.
3. If `IFD0:SubfileType` is `Reduced-resolution image` and `IFD0:Compression` is `JPEG`, extract bytes from the source file using `IFD0:StripOffsets` and `IFD0:StripByteCounts`.
4. Verify the extracted bytes are a JPEG, usually starting with `FF D8`.
5. If unavailable, generate a thumbnail through RAW decoding with libraw/rawpy.
6. Keep the RAW file as the source object for final file operations.

Observed from a sample Hasselblad `.3FR`:

- File size: around 203 MB.
- Embedded JPEG preview exists.
- Preview size: `3888 x 2918`, around 1.9 MB.
- RAW data size: `11904 x 8842`, 16-bit.
- Standard EXIF time exists.
- Standard EXIF GPS may be absent.
- ExifTool can read the IFD0 preview metadata, but `exiftool -b -PreviewImage`, `-JpgFromRaw`, and `-ThumbnailImage` may return empty for this file.
- The usable preview can still be extracted by cutting bytes from `IFD0:StripOffsets` with length `IFD0:StripByteCounts` when IFD0 is JPEG-compressed.

Example `.3FR` preview extraction logic:

```text
metadata = exiftool -json -n file.3FR
if IFD0:Compression == JPEG and IFD0:StripOffsets and IFD0:StripByteCounts:
    seek source file to StripOffsets
    read StripByteCounts bytes
    validate JPEG SOI/EOI
    write preview cache
```

### HEIC / HEIF

HEIC files can usually be decoded directly on macOS through ImageIO/CoreGraphics or `sips`. Unlike RAW files, there is usually no need to look for an embedded RAW preview first.

Preferred strategy:

1. Read metadata from the HEIC container with ExifTool.
2. Try direct preview extraction with `exiftool -b -PreviewImage`.
3. If a preview exists, cache it directly as the analysis image.
4. If no preview exists, decode the HEIC image into a cached JPEG preview, for example long edge `1600px`, using `pillow-heif` + Pillow or macOS ImageIO.
5. Use the cached JPEG preview for embedding, IQA, face detection, and UI display.
6. Keep the original `.HEIC` as the source object for final keep/move operations.

Observed from a sample Hasselblad `.HEIC`:

- File size: around 19 MB.
- Image size: `11656 x 8742`.
- Bit depth/profile: HEVC Main 10 / 10-bit HEIF.
- Camera: `Hasselblad CFV 100C/907X`.
- Standard capture time exists.
- Standard EXIF GPS may be absent.
- ExifTool exposes `PreviewImage` for this file.
- `exiftool -b -PreviewImage` extracts a usable JPEG preview of `3888 x 2918`, around 1.1 MB.

Example HEIC preview extraction command:

```bash
exiftool -b -PreviewImage input.HEIC > preview.jpg
```

Example macOS fallback thumbnail command:

```bash
sips -s format jpeg -Z 1600 input.HEIC --out preview.jpg
```

Note: with `sips`, specify `-s format jpeg`; otherwise the output may remain HEIC even if the path ends with `.jpg`.

Important metadata:

- `DateTimeOriginal` / capture time.
- file name and sequence order.
- camera model.
- lens model.
- focal length.
- exposure time.
- aperture.
- ISO.
- orientation.
- GPS if available.
- sidecar XMP rating/GPS if available.

## Clustering Strategy

Use time as the main boundary and visual embeddings inside time windows.

### Stage 1: Time Sessions

Sort photos by capture time and split into sessions.

Suggested initial rules:

- gap <= 2 minutes: same candidate session;
- 2-10 minutes: only cluster if visual similarity is very high;
- gap > 10 minutes: default new session;
- GPS, if available, can relax or strengthen boundaries;
- large changes in lens/focal length may help split sessions.

Reason: pure embedding can incorrectly group the same person across different scenes.

### Stage 2: Visual Clustering Within Sessions

Within each session:

- compute image embedding from preview/thumbnail;
- use approximate nearest neighbor or pairwise similarity for small sessions;
- cluster near-duplicates and same-scene variants;
- avoid over-merging portraits with different backgrounds or compositions.

Potential embeddings:

- CLIP image embedding;
- DINO/DINOv2 image embedding;
- traditional perceptual hash for near-duplicate prefiltering.

## Candidate Recommendation

The goal is not to find the objectively best image globally. The goal is to recommend likely keepers inside a near-duplicate cluster.

### Hard Filters

Downrank or exclude obvious failures:

- severe blur;
- overexposure or underexposure;
- extreme noise;
- unreadable/corrupt files;
- faces with closed eyes;
- subjects too small or badly cropped, when detectable.

### Technical Quality Score

Initial components:

- sharpness: Laplacian variance, Tenengrad, or high-frequency energy;
- exposure: highlight clipping and shadow clipping;
- contrast: local contrast distribution;
- noise: estimate from flat regions;
- color: severe color cast detection;
- orientation-aware preview normalization.

### Portrait and Face Score

If faces are detected, face quality should dominate general aesthetics.

Useful signals:

- face detected;
- eye-open score;
- face sharpness, especially around eyes;
- face pose/yaw/pitch;
- face size;
- occlusion or bad crop;
- for group photos, number of acceptable faces.

Candidate tools:

- MediaPipe Face Detection / Face Mesh;
- YuNet;
- RetinaFace;
- InsightFace.

### IQA / Aesthetic Score

Use local open-source IQA models as optional scoring components, not as the only decision maker.

Candidates:

- BRISQUE / NIQE / PIQE for lightweight technical quality;
- NIMA for aesthetic scoring;
- MUSIQ for stronger no-reference quality assessment;
- MANIQA or TOPIQ for slower re-ranking.

Suggested pipeline:

1. Use rules and traditional metrics for all images.
2. Run heavier IQA only on top candidates per cluster.
3. Combine IQA with face/technical/diversity signals.

### Diversity-Aware Selection

Do not simply choose the top 3 scores. They may be almost identical.

Use MMR-style selection:

```text
score = lambda * quality_score - (1 - lambda) * max_similarity_to_selected
```

This gives:

- best overall shot;
- alternative expression or pose;
- slightly different composition if still high quality.

## Suggested Scoring Formula

Initial generic score:

```text
final_score =
  0.30 * sharpness_score +
  0.20 * exposure_score +
  0.20 * subject_or_face_score +
  0.20 * iqa_or_aesthetic_score +
  0.10 * diversity_score
```

For portrait clusters:

```text
subject_or_face_score should increase to around 0.35
```

For landscape clusters:

```text
exposure_score and iqa_or_aesthetic_score should increase
```

## UI Design

Cullary should feel like a culling taskbench, not a general gallery.

### Task Home

Show scan result summary:

- total photos;
- number of clusters;
- number of likely rejected photos;
- estimated space reclaimable;
- number of high-confidence clusters;
- number of clusters needing review.

Primary actions:

- start review;
- view all clusters;
- review high-confidence clusters;
- review uncertain clusters.

### Cluster List

Each cluster card should show:

- cluster id;
- time range;
- approximate location if available;
- photo count;
- recommended keeper count;
- estimated reclaimable storage;
- confidence;
- 3-5 thumbnails.

Useful sorting:

- largest reclaimable storage;
- most photos;
- highest confidence;
- chronological order.

### Cluster Review Page

Recommended layout:

```text
Top: recommended keepers
Middle: 1v1 comparison area
Bottom: all photos in the cluster as thumbnails
```

Default state:

- recommended candidates are marked keep;
- all others are marked staging/delete;
- user corrects the recommendation.

Actions:

- confirm cluster;
- keep more;
- replace keeper;
- enter 1v1 mode;
- next cluster;
- undo.

### 1v1 Mode

Useful for portraits, expressions, action shots, and ambiguous clusters.

Flow:

```text
current champion vs challenger
user chooses left, right, both, or neither
```

Keyboard shortcuts can be added later:

- left arrow: left is better;
- right arrow: right is better;
- up arrow: keep both;
- down arrow: keep neither / skip;
- space: zoom;
- enter: confirm cluster.

## Safety Model

Never permanently delete in the MVP.

Recommended behavior:

- move rejected files to `.to_delete/`;
- preserve folder structure where possible;
- generate a JSON or CSV decision log;
- support undo before final cleanup;
- make sidecar files follow the original RAW when moved.

## Architecture Direction

A simple first architecture:

- scanner: walks folders and detects files;
- metadata extractor: reads EXIF/XMP and RAW preview info;
- preview cache: stores extracted JPEG previews/thumbnails;
- feature extractor: computes embeddings and quality metrics;
- clusterer: creates sessions and clusters;
- scorer: ranks keepers;
- review database: stores decisions;
- UI: task home, cluster list, cluster review;
- file operator: moves rejected files safely.

Implementation options:

- Python backend for image processing and ML;
- SQLite for local cache/decisions;
- desktop UI via Tauri, Electron, or a local web app;
- separate worker process for long-running scans.

## Open Questions

- Which UI shell should be used: Tauri, Electron, or local web app?
- Which embedding model is best on Apple Silicon for local speed/quality?
- Should `.3FR` preview extraction be implemented directly or delegated to libraw/exiftool/rawpy?
- How should sidecar files be detected and moved?
- What confidence threshold is safe enough for quick-confirm mode?
