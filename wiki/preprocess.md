# Preprocess Pipeline

Cullary's first preprocessing implementation uses a local cache directory and JSONL manifest instead of SQLite.

## Cache Layout

```text
.cullary_cache/
  previews/
    <source_id>.jpg
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

The source photos are read-only. Generated previews and analysis files are safe to delete and regenerate.

## CLI

```bash
python3 scripts/preprocess.py /Users/liubin/Desktop/TestImage
```

Useful options:

```bash
python3 scripts/preprocess.py /path/to/photos --cache-dir .cullary_cache
python3 scripts/preprocess.py /path/to/photos --force
```

## Analyzer Contract

Each analyzer records:

- `status`: `success`, `skipped`, or `failed`
- `version`
- `duration_ms`
- `error_message`
- `output_path` when a separate output file is written
- `data` for small inline fields

Analyzer failures are isolated. For example, missing model dependencies should not block metadata or preview extraction.

## Current Analyzer Layers

- Metadata: ExifTool JSON.
- Preview: JPEG copy, ExifTool embedded preview, `.3FR` IFD0 byte slicing, or HEIC `sips` fallback.
- Hash: optional Pillow + NumPy aHash/dHash.
- Quality: optional Pillow + NumPy.
- IQA: lightweight proxy based on quality metrics.
- Embedding / face: scaffolded as optional analyzers so the storage contract is stable before selecting Mac mini M4 models.

## Mac mini M4 Model Policy

Default model analyzers must be fast and smooth on Mac mini M4. Heavy IQA or face models should be used later only for candidate re-ranking, not the full first-pass pipeline.
