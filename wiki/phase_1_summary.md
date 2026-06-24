# Phase 1 总结：本地预处理 Pipeline

更新时间：2026-06-24

Phase 1 已经把 Phase 0 验证过的 metadata、preview、图像统计、embedding、face、IQA 能力接入正式本地 pipeline。输入是一个图片文件夹，输出是该文件夹下的 `.cullary/` 缓存目录。Phase 1 不做聚类、不做推荐、不移动源文件。

## 当前结论

当前实现已经满足 Phase 1 的核心目标：

- 可以从图片目录生成完整 `.cullary/` 本地分析缓存。
- 支持重复运行、cache hit、单文件 stale 后重算。
- 所有 analyzer 都有明确状态、版本、配置 hash、耗时、错误信息和输出路径。
- 前端可以通过 `task_state.json` 轮询任务状态，通过 `manifest.jsonl` 渲染列表。
- 基础阶段已按配置并行，embedding 已支持 batch 推理。
- 模型 analyzer 失败不会阻塞 metadata / preview / image metrics 等基础结果。

当前测试目录：

```text
/Users/liubin/Desktop/TestImage
```

当前缓存目录：

```text
/Users/liubin/Desktop/TestImage/.cullary
```

## 代码入口与结构

正式入口：

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /Users/liubin/Desktop/TestImage
```

安装本地包后也可以使用：

```bash
/opt/anaconda3/envs/hippo/bin/python -m pip install -e .
cullary-preprocess /Users/liubin/Desktop/TestImage
```

核心代码结构：

```text
src/cullary/
  analyzers/
    media.py          # metadata / preview / thumb
    hash.py           # aHash / dHash / pHash
    image_metrics.py  # exposure / contrast / color / sharpness / composition
    embedding.py      # DINOv2-small embedding
    face.py           # YuNet face metrics
    iqa.py            # PIQE IQA
  preprocessing/
    __main__.py
    cli.py
    pipeline.py       # pipeline orchestration / state / manifest
    progress.py       # text/jsonl/quiet progress output
  constants.py
  domain.py
  features.py
  state.py
  utils.py
```

`scripts/` 只保留验证、benchmark、smoke、下载模型等辅助脚本，不再放核心业务逻辑。

## Pipeline 执行流程

Phase 1 使用 stage-wise pipeline：

```text
scan
  -> metadata
  -> preview
  -> thumb
  -> hash
  -> image_metrics
  -> embedding
  -> face
  -> iqa
  -> summary
```

这样做的原因：

- 前端可以按阶段展示进度。
- 模型类 analyzer 可以在阶段内复用模型实例。
- 中断恢复时可以按 analyzer status 判断是否跳过。
- 单个 analyzer 失败不会影响其他 analyzer。

### scan

职责：

- 遍历输入目录。
- 识别支持格式：`.jpg`、`.jpeg`、`.heic`、`.heif`、`.3fr`。
- 忽略 `.DS_Store`、`.crdownload`、`.cullary/`、`.cullary_cache/`。
- 为每张图生成 `source_id` 和人可读 `display_id`。

当前样本结果：

```text
processable: 113
ignored: .DS_Store 1, .crdownload 4
by_extension: .3fr 83, .heic 30
```

### metadata

职责：

- 使用 ExifTool 读取源文件 metadata。
- 写入 `analysis/<display_id>/metadata.raw.json`。
- 在 `analysis.json` 中保留常用字段：相机、镜头、尺寸、拍摄时间、ISO、光圈、快门、焦距等。

并行策略：

```text
ThreadPoolExecutor, workers=4
```

### preview

职责：

- 为后续分析生成 JPEG preview。
- `.3FR` 优先尝试 ExifTool binary tag，失败后使用 IFD0 byte slice。
- `.HEIC` 当前样本使用 ExifTool `PreviewImage` 成功。
- preview 默认长边：1600。

并行策略：

```text
ThreadPoolExecutor, workers=4
```

当前样本 preview 方法：

```text
3fr_ifd0_byte_slice: 83
exiftool:PreviewImage: 30
```

### thumb

职责：

- 从 preview 生成 UI 列表缩略图。
- thumb 默认长边：360。

并行策略：

```text
ProcessPoolExecutor, workers=4
```

### hash

职责：

- 从 preview 计算近重复辅助特征。
- 输出：`ahash`、`dhash`、`phash`。

并行策略：

```text
ProcessPoolExecutor, workers=4
```

### image_metrics

职责：

从 cached preview 计算非模型图像指标，默认分析长边：1024。

输出大类：

- `exposure`：亮度、死黑、死白、动态范围 proxy。
- `contrast`：灰度标准差比例。
- `color`：饱和度、RGB 均值、偏色、白平衡 proxy。
- `sharpness`：Laplacian、Tenengrad、边缘密度、中心清晰度。
- `composition`：宽高比、方向、中心亮度。
- `experimental`：噪声 proxy、运动模糊方向性 proxy。

并行策略：

```text
ProcessPoolExecutor, workers=4
```

### embedding

职责：

- 使用默认单一 embedding 模型生成视觉向量。
- 当前默认：DINOv2-small。
- 输出 384 维归一化 `.npy` 向量。
- 向量只写文件，不放入 manifest。

模型配置：

```json
{
  "model": "dinov2-small",
  "model_version": "facebook/dinov2-small",
  "input_size": "processor_default",
  "normalize": true,
  "batch_size": 8
}
```

执行策略：

```text
workers=1, batch_size=8
```

当前样本检查：

```text
embedding files: 113
shape: (384,)
L2 norm min/max/mean: 1.0 / 1.0 / 1.0
```

### face

职责：

- 使用 OpenCV YuNet 检测人脸。
- 输出 face count、box、score、area ratio、center、5 点 landmarks、eye distance、eye angle、face sharpness、alignment score。

执行策略：

```text
workers=1
```

当前样本结果：

```text
photos_with_faces: 39
max_face_count: 3
```

### iqa

职责：

- 使用 PIQE 输出无参考图像质量分数。
- 默认输入长边：512。
- 分数方向：`lower_is_better`。

执行策略：

```text
workers=1
```

当前样本结果：

```text
PIQE min: 18.326
PIQE max: 50.006
PIQE mean: 34.291
```

### summary

职责：

- 汇总阶段耗时、成功/失败统计、忽略文件、工具路径、模型目录、输出文件路径。
- 写入 `run_summary.json`。
- 将 `task_state.json` 更新为最终状态。

## 并行与状态写入策略

当前并行配置在 `config/preprocess.default.json`：

```json
{
  "pipeline": {
    "default_workers": 1,
    "stage_workers": {
      "metadata": 4,
      "preview": 4,
      "thumb": 4,
      "hash": 4,
      "image_metrics": 4,
      "embedding": 1,
      "face": 1,
      "iqa": 1
    }
  }
}
```

原则：

- worker 只负责计算 analyzer payload/status。
- `task_state.json`、`manifest.jsonl`、`analysis.json` 只由主进程写。
- 基础阶段可并行，模型阶段默认保守，避免重复加载模型和内存抖动。
- embedding 用 batch 提升吞吐，而不是多进程加载多份模型。

## 产出目录结构

```text
<input_folder>/.cullary/
  config.snapshot.json
  task_state.json
  manifest.jsonl
  run_summary.json
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
      iqa_piqe_input.jpg
  logs/
```

当前样本计数：

```text
manifest.jsonl: 113
analysis.json: 113
metadata.raw.json: 113
iqa_piqe_input.jpg: 113
previews: 113
thumbs: 113
embeddings: 113
```

## manifest.jsonl

定位：列表页、任务恢复、快速状态读取。

每行一张图，主要字段：

```json
{
  "schema_version": "1.0",
  "source_id": "2338513848ebbf89e1f9",
  "display_id": "B0007059_3FR",
  "source": {
    "path": "/Users/liubin/Desktop/TestImage/B0007059.3FR",
    "relative_path": "B0007059.3FR",
    "file_name": "B0007059.3FR",
    "extension": ".3fr",
    "size": 211251200,
    "mtime_ns": 1759304932000000000
  },
  "assets": {
    "preview_path": ".cullary/previews/B0007059_3FR.jpg",
    "preview_width": 1600,
    "preview_height": 590,
    "thumb_path": ".cullary/thumbs/B0007059_3FR.jpg",
    "thumb_width": 360,
    "thumb_height": 133,
    "preview_method": "3fr_ifd0_byte_slice"
  },
  "analysis_path": ".cullary/analysis/B0007059_3FR/analysis.json",
  "status": {
    "overall": "success",
    "metadata": "success",
    "preview": "success",
    "thumb": "success",
    "hash": "success",
    "image_metrics": "success",
    "embedding": "success",
    "face": "success",
    "iqa": "success"
  },
  "ui_summary": {
    "orientation": "landscape",
    "face_count": 0,
    "quality_label": "normal",
    "warning_flags": []
  }
}
```

UI 使用约定：

- grid/list 使用 `thumb_path`。
- review/compare 使用 `preview_path`。
- 列表页只读 manifest。
- 详情页按需读取 `analysis_path`。

## analysis.json

定位：单张照片完整分析结果。

顶层结构：

```json
{
  "schema_version": "1.0",
  "source_id": "...",
  "display_id": "...",
  "source": {},
  "assets": {},
  "metadata": {},
  "hash": {},
  "image_metrics": {},
  "embedding": {},
  "face_metrics": {},
  "iqa_metrics": {},
  "score_features": {},
  "analyzer_status": {}
}
```

### analyzer_status

每个 analyzer 都记录：

```json
{
  "status": "success",
  "version": "image-metrics-v1",
  "config_hash": "af0c5707ebcd",
  "duration_ms": 50,
  "started_at": "2026-06-24T10:08:33+08:00",
  "finished_at": "2026-06-24T10:08:33+08:00",
  "error_message": null,
  "output_path": ".cullary/analysis/B0007772_HEIC/analysis.json"
}
```

跳过条件：

- 源文件 `size` 和 `mtime_ns` 未变化。
- analyzer `version` 未变化。
- analyzer `config_hash` 未变化。
- 上次状态是 `success`。
- 输出文件仍存在。

### image_metrics

当前大类和字段：

```text
input:
  max_side, analysis_width, analysis_height, scale

exposure:
  brightness_mean, brightness_median,
  brightness_p01, brightness_p05, brightness_p95, brightness_p99,
  shadow_clip_ratio, highlight_clip_ratio,
  dynamic_range_p05_p95

contrast:
  contrast_std_ratio

color:
  saturation_mean, saturation_median, saturation_clip_ratio,
  value_mean, rgb_mean,
  color_cast_rgb_deviation, color_cast_strength,
  white_balance_deviation

sharpness:
  laplacian_var, tenengrad, edge_density,
  center_laplacian_var, center_tenengrad,
  center_sharpness_ratio

composition:
  aspect_ratio, orientation,
  center_brightness_mean, center_brightness_delta

experimental:
  noise_proxy, gradient_anisotropy, dominant_angle_deg
```

### embedding

```json
{
  "model": "dinov2-small",
  "model_version": "facebook/dinov2-small",
  "kind": "vision",
  "dim": 384,
  "input_size": "processor_default",
  "batch_size": 8,
  "normalized": true,
  "vector_path": ".cullary/embeddings/B0007772_HEIC.npy",
  "preview_source": "preview_path"
}
```

### face_metrics

```json
{
  "model": "yunet",
  "input": {"max_side": 1280, "scale": 0.8},
  "face_count": 1,
  "largest_face_area_ratio": 0.00876057,
  "faces": [
    {
      "box": {"x": 566.85, "y": 469.2, "w": 111.01, "h": 151.65},
      "score": 0.920309,
      "area_ratio": 0.00876057,
      "center": {"x": 622.35, "y": 545.02},
      "landmarks": {
        "left_eye": [607.01, 529.27],
        "right_eye": [659.95, 526.57],
        "nose": [646.0, 558.79],
        "left_mouth": [614.21, 580.9],
        "right_mouth": [655.96, 578.36]
      },
      "eye_distance": 53.0117,
      "eye_angle_deg": -2.9229,
      "sharpness_laplacian_var": 537.739,
      "alignment_score": 0.935046
    }
  ]
}
```

### iqa_metrics

```json
{
  "input": {
    "max_side": 512,
    "path": ".cullary/analysis/B0007772_HEIC/iqa_piqe_input.jpg"
  },
  "metrics": {
    "piqe": {
      "score": 44.326324,
      "direction": "lower_is_better"
    }
  }
}
```

### score_features

Phase 1 只建立评分特征框架，不计算最终推荐分数。

当前大类：

```text
technical_quality:
  sharpness, exposure, contrast, color

face_quality:
  face_sharpness, face_size, alignment, detection_confidence

iqa:
  piqe

composition:
  center_sharpness, center_brightness, orientation
```

## task_state.json

定位：前端轮询任务进度。

关键字段：

```json
{
  "schema_version": "1.0",
  "task_id": "2026-06-24-100820-TestImage",
  "folder": "/Users/liubin/Desktop/TestImage",
  "cache_dir": "/Users/liubin/Desktop/TestImage/.cullary",
  "status": "success",
  "current_stage": "summary",
  "totals": {
    "discovered": 113,
    "processable": 113,
    "completed": 113,
    "failed": 0,
    "skipped": 0
  },
  "stages": {
    "metadata": {"status": "success", "done": 113, "total": 113},
    "preview": {"status": "success", "done": 113, "total": 113},
    "embedding": {"status": "success", "done": 113, "total": 113}
  },
  "errors": []
}
```

## run_summary.json

定位：本次运行的最终报告。

当前样本结果：

```text
status: success
total_photos: 113
failures: 0
duration_ms: 29309
per_100_estimate_ms: 25937
```

阶段耗时：

```text
metadata: 1772ms
preview: 9777ms
thumb: 454ms
hash: 484ms
image_metrics: 1589ms
embedding: 7581ms
face: 3625ms
iqa: 3998ms
```

Analyzer 成功统计：

```text
metadata: 113 success
preview: 113 success
thumb: 113 success
hash: 113 success
image_metrics: 113 success
embedding: 113 success
face: 113 success
iqa: 113 success
```

## 验证方式

输出契约验证：

```bash
/opt/anaconda3/envs/hippo/bin/python scripts/verify_phase1_outputs.py /Users/liubin/Desktop/TestImage
```

完整 smoke：

```bash
scripts/smoke_phase1.sh /Users/liubin/Desktop/TestImage
```

已验证内容：

- 输出目录和文件完整。
- manifest、task_state、run_summary 状态一致。
- 每张图 analyzer 状态均为 success。
- preview/thumb 文件存在且尺寸匹配 manifest。
- embedding `.npy` shape 正确、数值 finite、L2 norm 为 1。
- image_metrics 关键字段存在且为有限数值。
- face_count 类型正确。
- PIQE 分数存在且为有限数值。
- 重复运行可跳过未变化结果。
- 删除单张 analysis 后只修复该图。
- 修改单张源文件后只重算该图相关 analyzer。
- 修改 analyzer 配置后只重算对应 analyzer。
- embedding 模型缺失时基础 analyzer 不受影响，任务变为 `partial_success`。
- `.cullary/` 和 `.cullary_cache/` 不会被当作源图扫描。

## 当前注意点

- `score_features` 目前只保留大类和权重框架，子项 `value` 仍为 `null`。最终评分、归一化和推荐解释在后续阶段实现。
- `run_summary.skipped` 当前只记录 analyzer status 为 `skipped` 的原因列表；cache-hit 的 skipped 主要体现在 `stage_runtime.<stage>.skipped`，不展开到每张图列表。
- `logs/` 目录目前预留，当前没有写额外日志文件。
- 当前 face 不做 face embedding / 同人聚类；后续如果进入人物聚类，再增加独立 analyzer。
- 当前 IQA 默认只使用 PIQE；BRISQUE/NIQE/NRQM 等不进入全量默认路径。

## Phase 1 之后

Phase 1 输出已经可以支撑后续阶段：

- 聚类阶段可使用 time metadata、hash、embedding、preview path。
- 推荐阶段可使用 image_metrics、face_metrics、iqa_metrics 和 score_features 框架。
- UI 可以用 manifest + thumb 先构建列表，用 analysis_path 按需进入详情。
