# Cullary Road Map

This roadmap is a living document. It should be updated as implementation choices, model choices, and product priorities become clearer.

## Product Direction

Cullary is a local-first photo culling taskbench.

The first usable product should not be a simple file browser with later AI add-ons. It should be designed from the beginning around an intelligent analysis pipeline:

```text
source photo
  -> metadata extraction
  -> preview extraction
  -> visual embedding
  -> face analysis
  -> image quality / aesthetic analysis
  -> clustering
  -> keeper recommendation
  -> human review
  -> safe staging
```

The implementation can start small, but the architecture should assume these analysis outputs exist from day one.

## Guiding Principles

- Keep the original source files untouched until the user confirms actions.
- Separate source files from cached analysis previews.
- Treat embedding, face analysis, and IQA as core capabilities, not future bolt-ons.
- Prefer explainable recommendations over opaque ranking.
- Make every file operation reversible in the MVP.
- Optimize for local/NAS archive cleanup, not full catalog management.

## Phase 0: Sample Validation and Technical Probes

Goal: prove that the core media formats can be read and analyzed locally.

Tasks:

- Collect representative `.jpg`, `.jpeg`, `.heic`, and `.3fr` samples.
- Validate metadata extraction with ExifTool.
- Validate preview extraction for Hasselblad `.3FR` and `.HEIC`.
- Confirm preview orientation, dimensions, and color handling.
- Benchmark basic preview extraction speed on realistic folders.
- Decide the first local runtime path for image processing and ML.

Exit criteria:

- A CLI can scan a folder and produce cached JPEG previews plus metadata records.
- `.3FR` preview extraction has a working direct-preview or byte-slice path.
- HEIC fallback decoding path is confirmed.

## Phase 1: Analysis Schema and Local Cache

Goal: define the durable data model before building UI or recommendation logic.

Core records:

- photo source record;
- metadata record;
- preview cache record;
- perceptual hash record;
- visual embedding record;
- quality metrics record;
- face metrics record;
- IQA / aesthetic score record;
- cluster record;
- recommendation record;
- user decision record;
- file operation log.

Tasks:

- Create SQLite schema for scan/cache/analysis/decision data.
- Store analyzer version and model version with each analysis result.
- Support incremental scan by file path, size, mtime, and optionally hash.
- Make analyzer outputs nullable so slow or failed analyzers do not block the whole task.
- Design a re-analysis path when model versions change.

Exit criteria:

- The system can persist complete scan and analysis state locally.
- Re-running a scan avoids unnecessary repeated work.
- Failed analysis steps are visible and recoverable.

## Phase 2: First Intelligent Analyzer Pipeline

Goal: connect real first-version analyzers early, even if later models improve.

Initial analyzers:

- preview extractor;
- metadata extractor;
- perceptual hash;
- visual embedding, preferably DINOv2 or CLIP;
- traditional quality metrics such as sharpness, exposure clipping, contrast, and corruption checks;
- face detection and basic face quality;
- lightweight IQA / aesthetic score.

Tasks:

- Implement a worker-style analyzer pipeline.
- Cache intermediate outputs.
- Record analyzer errors per photo.
- Benchmark analyzer speed separately from UI.
- Keep model choice swappable behind stable interfaces.

Exit criteria:

- Every scanned photo has a preview, metadata, embedding, quality metrics, and analyzer status.
- Face and IQA fields exist even if some formats or photos produce no result.
- Analyzer results are usable by clustering and recommendation.

## Phase 3: Clustering

Goal: group photos into reviewable near-duplicate or same-scene clusters.

Strategy:

```text
capture time sessions
  -> visual similarity inside session
  -> near-duplicate / same-scene clusters
```

Tasks:

- Split photos into time sessions.
- Use visual embeddings for similarity within sessions.
- Use pHash as a near-duplicate helper, not the only clustering signal.
- Avoid merging visually similar subjects across different scenes.
- Persist cluster confidence and cluster reason signals.

Exit criteria:

- Clusters are good enough for human review on real sample folders.
- The system can explain why photos were grouped.
- Bad clusters can be inspected and later corrected.

## Phase 4: Recommendation Engine

Goal: recommend likely keepers inside each cluster with explainable reasons.

Scoring inputs:

- sharpness;
- exposure;
- contrast;
- face presence and face quality;
- eye / expression warnings when available;
- IQA / aesthetic score;
- visual diversity among selected keepers;
- metadata context when useful.

Tasks:

- Implement a weighted scoring formula.
- Support different weighting profiles for portraits, landscapes, and burst/action sets.
- Select 1-3 keepers per cluster based on cluster size and diversity.
- Generate recommendation reasons and warnings.
- Store recommendation confidence.

Exit criteria:

- Each cluster has default keep/reject marks.
- Recommendations include human-readable reasons.
- The user can override recommendations without fighting the system.

## Phase 5: Review UI

Goal: let the user efficiently inspect clusters and confirm or change recommendations.

Core screens:

- task summary;
- cluster list;
- cluster review page;
- optional 1v1 compare mode.

Tasks:

- Show recommended keepers and rejected candidates clearly.
- Show recommendation reasons, warnings, and confidence.
- Support keep more, replace keeper, reject, confirm cluster, undo, and next cluster.
- Add keyboard shortcuts after the basic flow works.
- Keep UI focused on culling, not general gallery browsing.

Exit criteria:

- A user can complete a full culling task from scan to confirmed decisions.
- Recommendation reasons are visible enough to build trust.
- Manual correction is fast.

## Phase 6: Safe File Operations

Goal: safely move rejected files without permanent deletion.

Tasks:

- Move rejected photos to `_to_delete/`.
- Preserve source folder structure where possible.
- Move sidecar files with the source file.
- Generate JSON or CSV decision logs.
- Support undo before final cleanup.
- Never permanently delete files in the MVP.

Exit criteria:

- Confirmed rejects are staged safely.
- The operation is logged and reversible.
- Source files and sidecars stay consistent.

## Phase 7: Quality Iteration and Productization

Goal: improve real-world usefulness after the core loop works.

Possible improvements:

- stronger embedding model;
- better face model;
- stronger IQA model such as MUSIQ, MANIQA, or TOPIQ;
- cluster correction UI;
- high-confidence quick confirm mode;
- 1v1 tournament mode;
- large-folder and NAS performance improvements;
- background worker queue;
- failure diagnostics;
- export/import decision logs.

Exit criteria:

- Cullary is reliable on large real folders.
- Recommendations become trustworthy enough to reduce review time.
- The user can recover from model mistakes and file-operation mistakes.

## Near-Term Implementation Order

Recommended immediate order:

1. Validate preview and metadata extraction on real samples.
2. Define SQLite schema and analyzer result contracts.
3. Implement the first analyzer pipeline with embedding, face, and IQA fields included.
4. Implement time-session plus embedding-based clustering.
5. Implement explainable keeper recommendation.
6. Build the minimal review UI.
7. Add safe staging to `_to_delete/`.

## Open Decisions

- UI shell: Tauri, Electron, or local web app.
- First embedding model: DINOv2, CLIP, or another local model.
- First face analysis library: MediaPipe, YuNet, RetinaFace, or InsightFace.
- First IQA model: traditional BRISQUE/NIQE style metric or a learned model.
- Whether `.3FR` preview extraction should rely on ExifTool, direct byte slicing, libraw/rawpy, or a layered fallback.
- How sidecar files should be discovered and moved.
- What confidence level is safe for quick-confirm workflows.
