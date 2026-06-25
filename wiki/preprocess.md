# Preprocess Pipeline

Cullary Phase 1 的预处理实现已经拆成正式项目结构：核心业务代码在 `src/cullary/`，`scripts/` 只保留验证、smoke、benchmark 和模型下载脚本。

入口：

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /Users/liubin/Desktop/TestImage
```

CLI 默认向 stderr 输出简洁进度；给前端/服务端日志接入时可以使用 JSONL：

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /path/to/photos --progress jsonl
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /path/to/photos --quiet
```

安装成本地包后，正式 console 入口是：

```bash
/opt/anaconda3/envs/hippo/bin/python -m pip install -e .
cullary-preprocess /Users/liubin/Desktop/TestImage
```

实际执行链路：

```text
python -m cullary.preprocessing
  -> src/cullary/preprocessing/__main__.py
  -> src/cullary/preprocessing/cli.py
  -> src/cullary/preprocessing/pipeline.py
  -> src/cullary/analyzers/*
```

## Cache Layout

```text
<input_folder>/.cullary/
  previews/
    <display_id>.jpg
  thumbs/
    <display_id>.jpg
  embeddings/
    <display_id>.npy
  analysis/
    <display_id>/
      analysis.json
      metadata.raw.json
  manifest.jsonl
  task_state.json
  run_summary.json
  config.snapshot.json
```

The source photos are read-only. Generated previews and analysis files are safe to delete and regenerate.

## CLI

Useful options:

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /path/to/photos --force
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /path/to/photos --limit 20
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /path/to/photos --config config/preprocess.default.json
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
- Thumb: cached JPEG thumbnail for grid UI.
- Hash: Pillow + NumPy aHash/dHash/pHash.
- Image metrics: OpenCV/NumPy exposure, contrast, color, sharpness, composition, and experimental noise/motion proxies.
- Embedding: DINOv2-small via local Transformers model, vector written as `.npy`.
- Face: OpenCV YuNet face count, boxes, landmarks, area ratio, face sharpness, and alignment.
- IQA: PIQE via `pyiqa` on a resized input.

Analyzer failures are isolated. Model analyzer failures can make the run `partial_success`, but they do not block metadata, preview, thumb, hash, or image metrics.

## Parallel Policy

- `metadata` and `preview`: `ThreadPoolExecutor`, default 4 workers.
- `thumb`, `hash`, and `image_metrics`: `ProcessPoolExecutor`, default 4 workers.
- `embedding`: single worker with batch inference. `device=auto` prefers MPS, then CUDA, then CPU; default `mps_batch_size=4`, `cpu_batch_size=8`.
- `face` and `iqa`: single worker for stable model/runtime ownership.

Workers only compute analyzer payloads. The main process remains the only writer for `task_state.json`, `manifest.jsonl`, and per-photo `analysis.json`.

## Validation

```bash
/opt/anaconda3/envs/hippo/bin/python scripts/verify_phase1_outputs.py /Users/liubin/Desktop/TestImage
scripts/smoke_phase1.sh /Users/liubin/Desktop/TestImage
```

`scripts/smoke_phase1.sh` runs the real sample pipeline, verifies output contract, and runs the resume/stale behavior test.

## Mac mini M4 Model Policy

Default model analyzers must be fast and smooth on Mac mini M4. Embedding uses Torch MPS when available; YuNet face, MediaPipe person mask, and PIQE IQA do not use Torch MPS in the current default path. Heavy IQA or face models should be used later only for candidate re-ranking, not the full first-pass pipeline.
