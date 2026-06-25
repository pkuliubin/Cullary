# Phase 1 计划：本地分析 Pipeline 与任务状态系统

Phase 1 的目标是把 Phase 0 已验证的能力正式接入一个可中断、可恢复、可被 UI 查询状态的本地预处理 pipeline。

输入是一整个图片文件夹；输出是该文件夹下的 `.cullary/` 本地缓存与分析结果。Phase 1 不做聚类、不做推荐、不移动源文件。

## 目标边界

### Phase 1 要完成

- 扫描用户选择的图片文件夹。
- 在输入目录下创建 `.cullary/`，所有缓存与分析结果都写入这里。
- 为每张图片生成稳定 source record、preview、thumb、metadata、hash、image metrics、embedding、face metrics、IQA metrics。
- 支持中断继续：已成功完成且源文件、配置、analyzer 版本未变化的结果不重复计算。
- 维护任务状态，让前端可以轮询当前进度、阶段、失败原因。
- 保持分析结果 JSON 可读、可 diff、可追踪 analyzer 版本。

### Phase 1 不做

- 不做照片聚类。
- 不做最终推荐分数和 keeper/reject 决策。
- 不做文件移动、删除、改名。
- 不把源文件复制进缓存。
- 不使用 SQLite 作为默认状态存储。
- 不把多个 embedding 模型结果都写入正式分析结果；同类能力只保留一个默认模型输出。

## 缓存目录与模型目录

用户选择的图片目录：

```text
<input_folder>/
```

Phase 1 缓存目录：

```text
<input_folder>/.cullary/
  config.snapshot.json
  task_state.json
  manifest.jsonl
  run_summary.json
  previews/
  thumbs/
  analysis/
  embeddings/
  logs/
```

模型权重不放在每个图片目录下，使用全局模型缓存：

```text
~/.cullary/models/
```

可通过环境变量覆盖：

```text
CULLARY_MODEL_DIR=/path/to/models
```

这样做的原因：

- 每个照片任务的分析状态跟随照片目录，便于复制、备份、人工检查。
- 模型权重全局复用，避免每个相册重复下载大模型。

## 默认配置

配置文件建议放在：

```text
config/preprocess.default.json
```

第一版默认策略：

```json
{
  "cache": {
    "dir_name": ".cullary"
  },
  "models": {
    "model_dir": "~/.cullary/models"
  },
  "pipeline": {
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
  },
  "preview": {
    "long_edge": 1600
  },
  "thumb": {
    "long_edge": 360
  },
  "image_metrics": {
    "max_side": 1024
  },
  "embedding": {
    "enabled": true,
    "model": "dinov2-small",
    "model_version": "facebook/dinov2-small",
    "input_size": "processor_default",
    "normalize": true,
    "device": "auto",
    "device_fallback": true,
    "batch_size": 8,
    "cpu_batch_size": 8,
    "mps_batch_size": 4
  },
  "face": {
    "enabled": true,
    "model": "yunet",
    "max_side": 1280,
    "score_threshold": 0.6
  },
  "iqa": {
    "enabled": true,
    "metric": "piqe",
    "max_side": 512,
    "compare_metrics": []
  }
}
```

输入尺寸先按以上策略固化到配置里。后续如果效果或速度不理想，只改配置和 analyzer 版本，不改数据契约。

## 阶段划分

Phase 1 按 stage-wise pipeline 执行，而不是每张图一次性跑完所有 analyzer：

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

原因：

- 前端进度更清晰。
- 模型类 analyzer 可以按阶段加载一次模型，避免重复初始化。
- 中断恢复时可以明确知道哪个阶段、哪张图、哪个 analyzer 已完成。
- 失败隔离更直接，单个 analyzer 失败不影响其他 analyzer。

## 图片标识

输出目录和文件名使用人可读的 `display_id`：

```text
B0007796_HEIC
```

规则：

- 默认由源文件名生成，替换不适合路径的字符。
- 如果同目录或子目录里出现同名冲突，追加短 hash 后缀。
- 内部仍保留稳定 `source_id`，用于长期追踪。

示例：

```text
<input_folder>/.cullary/analysis/B0007796_HEIC/analysis.json
<input_folder>/.cullary/previews/B0007796_HEIC.jpg
<input_folder>/.cullary/thumbs/B0007796_HEIC.jpg
<input_folder>/.cullary/embeddings/B0007796_HEIC.npy
```

## 状态与恢复机制

每个 analyzer 都必须记录状态：

```json
{
  "status": "success",
  "version": "image-metrics-v1",
  "config_hash": "abc123",
  "duration_ms": 123,
  "started_at": "2026-06-23T17:00:00+08:00",
  "finished_at": "2026-06-23T17:00:01+08:00",
  "error_message": null,
  "output_path": ".cullary/analysis/B0007796_HEIC/analysis.json"
}
```

状态枚举：

```text
pending | running | success | skipped | failed | stale
```

跳过条件：

- 源文件 `size` 和 `mtime_ns` 未变化。
- analyzer `version` 未变化。
- analyzer `config_hash` 未变化。
- 输出文件存在且上次状态为 `success`。

重新计算条件：

- 源文件变化。
- analyzer 版本变化。
- analyzer 相关配置变化。
- 输出文件缺失或 JSON 损坏。
- 上次状态是 `failed`，且用户选择 retry。

中断恢复方式：

- 每个阶段按图片逐个写入 analyzer status。
- `task_state.json` 定期原子写入。
- `manifest.jsonl` 在阶段结束或安全 checkpoint 重写。
- 进程被杀后，下次启动读取现有 manifest 和 per-photo analysis，自动跳过已完成结果。

## 前端任务状态契约

前端发起任务：

```http
POST /api/preprocess/start
```

请求：

```json
{
  "folder": "/Users/liubin/Desktop/TestImage",
  "resume": true
}
```

返回：

```json
{
  "task_id": "2026-06-23-170000-TestImage",
  "cache_dir": "/Users/liubin/Desktop/TestImage/.cullary"
}
```

前端查询任务状态：

```http
GET /api/preprocess/tasks/<task_id>/status
```

返回内容直接对应 `.cullary/task_state.json`：

```json
{
  "schema_version": "1.0",
  "task_id": "2026-06-23-170000-TestImage",
  "folder": "/Users/liubin/Desktop/TestImage",
  "cache_dir": "/Users/liubin/Desktop/TestImage/.cullary",
  "status": "running",
  "current_stage": "embedding",
  "started_at": "2026-06-23T17:00:00+08:00",
  "updated_at": "2026-06-23T17:02:00+08:00",
  "totals": {
    "discovered": 46,
    "processable": 46,
    "completed": 31,
    "failed": 0,
    "skipped": 12
  },
  "stages": {
    "scan": {"status": "success", "done": 46, "total": 46},
    "metadata": {"status": "success", "done": 46, "total": 46},
    "preview": {"status": "success", "done": 46, "total": 46},
    "thumb": {"status": "success", "done": 46, "total": 46},
    "hash": {"status": "success", "done": 46, "total": 46},
    "image_metrics": {"status": "success", "done": 46, "total": 46},
    "embedding": {"status": "running", "done": 31, "total": 46},
    "face": {"status": "pending", "done": 0, "total": 46},
    "iqa": {"status": "pending", "done": 0, "total": 46}
  },
  "errors": []
}
```

第一版前端用 polling 即可；后续需要更顺滑体验时再加 SSE。

## Manifest 契约

`manifest.jsonl` 一行一张图，面向列表页和任务恢复，不放大字段和 embedding vector。

示例：

```json
{
  "schema_version": "1.0",
  "source_id": "f657b3528c719be69373",
  "display_id": "B0007796_HEIC",
  "source": {
    "path": "/Users/liubin/Desktop/TestImage/B0007796.HEIC",
    "relative_path": "B0007796.HEIC",
    "file_name": "B0007796.HEIC",
    "extension": ".heic",
    "size": 19993600,
    "mtime_ns": 1759404538000000000
  },
  "assets": {
    "preview_path": ".cullary/previews/B0007796_HEIC.jpg",
    "preview_width": 1600,
    "preview_height": 1200,
    "thumb_path": ".cullary/thumbs/B0007796_HEIC.jpg",
    "thumb_width": 360,
    "thumb_height": 270
  },
  "analysis_path": ".cullary/analysis/B0007796_HEIC/analysis.json",
  "status": {
    "overall": "partial",
    "metadata": "success",
    "preview": "success",
    "thumb": "success",
    "hash": "success",
    "image_metrics": "success",
    "embedding": "success",
    "face": "pending",
    "iqa": "pending"
  },
  "ui_summary": {
    "orientation": "landscape",
    "face_count": 1,
    "quality_label": "normal",
    "warning_flags": []
  }
}
```

UI 约定：

- grid / list 使用 `thumb_path`。
- review / compare 使用 `preview_path`。
- 列表页只读 manifest。
- 详情页按需读取 `analysis_path`。

## 单张分析结果契约

路径：

```text
<input_folder>/.cullary/analysis/<display_id>/analysis.json
```

顶层结构：

```json
{
  "schema_version": "1.0",
  "source_id": "f657b3528c719be69373",
  "display_id": "B0007796_HEIC",
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

## 数据维度

### Metadata

来源：ExifTool。

保留内容：

- 文件类型、尺寸、方向。
- 拍摄时间。
- 相机、镜头。
- 焦距、快门、光圈、ISO。
- 必要 raw metadata 可单独保存，避免主 JSON 过大。

用途：

- 时间上下文和后续聚类。
- UI 展示。
- 辅助解释照片差异。

### Hash

来源：Pillow / OpenCV / NumPy。

保留内容：

- `ahash`
- `dhash`
- `phash`

用途：

- 后续近重复辅助判断。
- 快速发现完全相同或极相似图片。

### Image Metrics

来源：cached preview 缩放后自行计算，不依赖模型。

正式结构按大类聚合，保留原始量纲：

```json
{
  "image_metrics": {
    "input": {
      "max_side": 1024,
      "analysis_width": 1024,
      "analysis_height": 768,
      "scale": 0.263374
    },
    "exposure": {
      "brightness_mean": 66.8,
      "brightness_median": 73.0,
      "brightness_p01": 3.0,
      "brightness_p05": 11.0,
      "brightness_p95": 120.0,
      "brightness_p99": 144.0,
      "shadow_clip_ratio": 0.0245,
      "highlight_clip_ratio": 0.0,
      "dynamic_range_p05_p95": 0.427
    },
    "contrast": {
      "contrast_std_ratio": 0.137
    },
    "color": {
      "saturation_mean": 0.208,
      "saturation_median": 0.203,
      "saturation_clip_ratio": 0.000015,
      "value_mean": 0.303,
      "rgb_mean": [62.6, 67.4, 74.1],
      "color_cast_rgb_deviation": [-5.4, -0.5, 6.0],
      "color_cast_strength": 0.0319,
      "white_balance_deviation": 0.168
    },
    "sharpness": {
      "laplacian_var": 75.0,
      "tenengrad": 821.9,
      "edge_density": 0.036,
      "center_laplacian_var": 51.3,
      "center_tenengrad": 862.8,
      "center_sharpness_ratio": 0.685
    },
    "composition": {
      "aspect_ratio": 1.332,
      "orientation": "landscape",
      "center_brightness_mean": 91.2,
      "center_brightness_delta": 24.4
    },
    "experimental": {
      "noise_proxy": 0.0034,
      "gradient_anisotropy": 0.443,
      "dominant_angle_deg": 87.56
    }
  }
}
```

用途：

- 技术质量评分输入。
- 后续推荐解释。
- 与 IQA 模型互补。

### Embedding

来源：DINOv2-small。

正式结果只保留一个默认 embedding：

```json
{
  "embedding": {
    "model": "dinov2-small",
    "model_version": "facebook/dinov2-small",
    "dim": 384,
    "input_size": "processor_default",
    "batch_size": 4,
    "device": "mps",
    "normalized": true,
    "vector_path": ".cullary/embeddings/B0007796_HEIC.npy",
    "preview_source": "preview_path"
  }
}
```

用途：

- Phase 3 聚类的主要视觉特征。
- 后续相似度搜索。

注意：

- vector 不写入 `analysis.json`，只写 `.npy`。
- CLIP / SigLIP / DINOv2-base 可作为 benchmark 和未来切换候选，不进入 Phase 1 默认正式输出。

### Face Metrics

来源：OpenCV YuNet。

```json
{
  "face_metrics": {
    "model": "yunet",
    "input": {
      "max_side": 1280,
      "scale": 0.329
    },
    "face_count": 2,
    "largest_face_area_ratio": 0.0095,
    "faces": [
      {
        "box": {"x": 1559.2, "y": 1206.0, "w": 270.0, "h": 402.1},
        "score": 0.9056,
        "area_ratio": 0.0095,
        "center": {"x": 1694.2, "y": 1407.0},
        "landmarks": {
          "left_eye": [1660.0, 1356.5],
          "right_eye": [1783.1, 1324.3],
          "nose": [1759.8, 1418.8],
          "left_mouth": [1710.5, 1508.1],
          "right_mouth": [1809.4, 1481.0]
        },
        "eye_distance": 127.17,
        "eye_angle_deg": -14.64,
        "sharpness_laplacian_var": 11.3,
        "alignment_score": 0.6748
      }
    ]
  }
}
```

用途：

- 人像照片组内选优。
- 人脸质量解释。
- 后续如需要同人聚类，再增加 face embedding analyzer。

### IQA Metrics

来源：PIQE。

```json
{
  "iqa_metrics": {
    "input": {
      "max_side": 512
    },
    "metrics": {
      "piqe": {
        "score": 31.28,
        "direction": "lower_is_better"
      }
    }
  }
}
```

用途：

- 作为技术质量和视觉缺陷的补充指标。
- 与传统 image metrics 对照。

BRISQUE / NIQE / NRQM 不进入默认全量 pipeline。后续可以作为调研或抽样对照。

## Score Features

Phase 1 可以产出归一化前的 score feature 框架，但不产出最终 recommendation。

原则：

- 原始指标保留原量纲。
- 归一化结果使用 0-1，越高越好。
- 大类有权重，大类下子项也可有权重。
- 最终权重和推荐逻辑放到 Phase 4。

结构：

```json
{
  "score_features": {
    "technical_quality": {
      "score": null,
      "components": {
        "sharpness": {"weight": 0.45, "value": null},
        "exposure": {"weight": 0.25, "value": null},
        "contrast": {"weight": 0.15, "value": null},
        "color": {"weight": 0.15, "value": null}
      }
    },
    "face_quality": {
      "score": null,
      "components": {
        "face_sharpness": {"weight": 0.4, "value": null},
        "face_size": {"weight": 0.25, "value": null},
        "alignment": {"weight": 0.2, "value": null},
        "detection_confidence": {"weight": 0.15, "value": null}
      }
    },
    "iqa": {
      "score": null,
      "components": {
        "piqe": {"weight": 1.0, "value": null}
      }
    },
    "composition": {
      "score": null,
      "components": {
        "center_sharpness": {"weight": 0.5, "value": null},
        "center_brightness": {"weight": 0.3, "value": null},
        "orientation": {"weight": 0.2, "value": null}
      }
    }
  }
}
```

## 实现步骤与验证方案

### Step 1：配置与目录系统

实现：

- 新增默认配置文件。
- 支持 CLI 参数传入输入目录和配置文件。
- 解析 `CULLARY_MODEL_DIR`。
- 创建 `<input_folder>/.cullary/` 目录结构。
- 写入 `config.snapshot.json`。

验证：

- 输入 `/Users/liubin/Desktop/TestImage` 后，缓存目录出现在该目录下。
- 项目根目录不再生成真实任务缓存。
- 删除 `.cullary/` 后可重新创建。
- 修改配置后 `config_hash` 发生变化。

### Step 2：扫描、ID 与 Manifest

实现：

- 扫描支持的图片格式。
- 忽略 `.DS_Store`、`.crdownload`、`.cullary/`、`.cullary_cache/`。
- 生成 `source_id` 和 `display_id`。
- 写入 `manifest.jsonl` 初始记录。
- 支持同名冲突处理。

验证：

- 测试样本扫描数量应与当前有效源图数量一致。
- `.DS_Store` 和 `.crdownload` 不进入 manifest。
- `display_id` 使用可读文件名。
- 人工制造同名冲突时，目录名不会覆盖。
- manifest 每行都是合法 JSON。

### Step 3：任务状态系统

实现：

- 新增 `task_state.json`。
- 每个阶段记录 `pending/running/success/failed/skipped`。
- 记录总数、完成数、失败数、跳过数。
- 原子写入状态文件。

验证：

- pipeline 运行中可以反复读取 `task_state.json`。
- 中断进程后，状态停留在最后 checkpoint。
- 重跑后会从已有结果恢复。
- 人为制造单张失败时，任务整体状态可继续推进，并记录错误。

### Step 4：Metadata Analyzer

实现：

- 使用 `exiftool -json -n` 读取 metadata。
- 将核心 metadata 写入 `analysis.json`。
- 可选 raw metadata 单独保存，避免主 JSON 过大。

验证：

- 当前测试样本 metadata 成功。
- 输出包含尺寸、拍摄时间、相机、镜头、曝光参数。
- ExifTool 不存在时给出清晰错误，不导致无提示失败。
- 重跑时 metadata 能跳过。

### Step 5：Preview 与 Thumb

实现：

- 生成 long edge 1600 的 JPEG preview。
- 生成 long edge 360 的 JPEG thumb。
- 记录宽高和路径。
- UI 列表只依赖 thumb，review 依赖 preview。

验证：

- 每张成功图片都有 preview 和 thumb。
- thumb 长边为 360 左右。
- preview 长边为 1600 左右。
- `manifest.jsonl` 中路径可被前端直接使用。
- UI benchmark 可使用 thumbs 渲染大列表。

说明：

- JPG/JPEG 和额外 fallback 后续再增强，不阻塞 Phase 1 的主契约。

### Step 6：Hash Analyzer

实现：

- 基于 preview 计算 `ahash/dhash/phash`。
- 写入 `analysis.json`。

验证：

- 当前测试样本 hash 成功。
- 重跑可跳过。
- 修改 preview 或配置后可触发重新计算。

### Step 7：Image Metrics Analyzer

实现：

- 基于 preview 缩放到长边 1024。
- 计算 exposure、contrast、color、sharpness、composition、experimental。
- 按大类写入 `image_metrics`。

验证：

- 当前测试样本全部成功。
- 输出字段覆盖 Phase 0 已验证指标。
- 数值无 NaN、Infinity。
- 耗时记录进入 analyzer status。
- 抽样对照 `scripts/benchmark_image_metrics.py` 的输出结构和量级。

### Step 8：Embedding Analyzer

实现：

- 默认使用 `DINOv2-small`。
- 从 `~/.cullary/models/` 或 `CULLARY_MODEL_DIR` 加载模型。
- 基于 preview 计算 normalized vector。
- vector 写入 `.cullary/embeddings/<display_id>.npy`。
- `analysis.json` 只记录模型、维度、路径、输入策略。

验证：

- 模型存在时，当前测试样本全量成功生成 384 维向量。
- `.npy` 可被 NumPy 正常读取。
- vector 不写入 manifest 或主 JSON。
- 模型缺失时，embedding analyzer 标记 failed，metadata/preview/image_metrics 不受影响。
- 重跑时不重复加载和计算已完成向量。

### Step 9：Face Analyzer

实现：

- 默认使用 OpenCV YuNet。
- 输入缩放到长边 1280。
- 输出 face count、box、score、landmarks、面积比例、眼距、角度、face sharpness、alignment score。
- 坐标映射回 preview 坐标。

验证：

- 当前测试样本全部完成处理。
- 无人脸图片也应是 `success`，`face_count=0`。
- 人脸样本输出结构稳定。
- 可选生成 debug overlay，但不作为正式 UI 必需资产。
- 模型文件缺失时只让 face analyzer failed，不影响其他 analyzer。

### Step 10：IQA Analyzer

实现：

- 默认使用 PIQE。
- 输入缩放到长边 512。
- 输出 `score` 和 `direction=lower_is_better`。

验证：

- 当前测试样本能完成或给出逐张失败原因。
- 输出值为有限数字。
- 耗时记录到 analyzer status。
- PIQE 缺包或运行失败时，不影响其他 analyzer。

### Step 11：Run Summary

实现：

- 任务结束写入 `run_summary.json`。
- 汇总每个阶段成功、失败、跳过、耗时。
- 汇总失败原因 top list。
- 记录运行环境、Python 路径、模型目录、配置快照 hash。

验证：

- 成功任务状态为 `success`。
- 部分 analyzer 失败时任务状态可为 `partial_success`。
- summary 能直接回答“哪些没跑成、为什么、耗时多少”。

### Step 12：CLI 与前端 API 预留

实现：

- CLI 先作为真实 pipeline 入口。
- 内部结构按 service/library 组织，后续 API 直接调用同一套逻辑。
- task state 文件作为前端 polling 的稳定契约。

验证：

- CLI 可执行完整任务。
- 前端无需解析日志，只读 `task_state.json` 和 `manifest.jsonl`。
- 同一个输入目录重复运行结果稳定。

## 端到端验收

使用样本目录：

```text
/Users/liubin/Desktop/TestImage
```

验收项：

- `.cullary/` 创建在样本目录下。
- `manifest.jsonl` 记录数与当前有效照片数量一致。
- 每张成功照片都有 `analysis.json`。
- 每张成功照片都有 preview 和 thumb。
- 每张成功照片都有 metadata、hash、image_metrics。
- embedding 成功时，每张照片都有 `.npy` vector。
- face 无人脸时也是成功状态。
- IQA 输出 PIQE 分数或明确失败原因。
- 中断后重跑不会重复处理已成功且未变化的 analyzer。
- 删除单张 analysis 后重跑只补这张或相关 analyzer。
- 修改配置后，只让受影响 analyzer 变 stale 并重算。
- 前端可通过 `task_state.json` 获取运行状态。

## 性能验证

Phase 1 需要记录端到端耗时，但不以性能优化作为阻塞主线。

当前并行策略：

- `metadata` / `preview` 使用 `ThreadPoolExecutor`，默认 4 workers。
- `thumb` / `hash` / `image_metrics` 使用 `ProcessPoolExecutor`，默认 4 workers。
- `embedding` 默认 `workers=1`，使用 batch 推理；`device=auto` 时优先 MPS，MPS 默认 `batch_size=4`，CPU 默认 `batch_size=8`。
- `face` / `iqa` 默认 `workers=1`，保持单进程模型实例和稳定输出。
- 所有 manifest、task_state、analysis 写入仍由主进程统一完成，worker 只返回 analyzer payload/status。

需要输出的统计：

- 每 100 张估算耗时。
- scan / metadata / preview / thumb / hash / image_metrics / embedding / face / iqa 分阶段耗时。
- cache 命中重跑耗时。
- 模型 analyzer 首次加载耗时。
- 单张平均、p50、p95。

验证方式：

- 先用当前测试样本真实跑通。
- 再用重复样本或更多真实目录做 100 张量级估算。
- 如果某阶段明显过慢，先通过配置降低输入尺寸或改并发策略，不改数据契约。

## 与 UI 需要确认的 Schema 点

需要和 UI 固化：

- `manifest.jsonl` 中路径使用 cache-relative path，还是 API 返回 file URL。
- grid/list 只使用 `thumb_path`。
- review/compare 只使用 `preview_path`。
- 列表页不加载 `analysis.json` 大字段。
- 详情页按需加载 `analysis_path`。
- `task_state.json` 是否满足首版 polling 需求。
- `ui_summary` 需要哪些轻量字段：orientation、face_count、quality_label、warning_flags。



## 当前代码结构

Phase 1 实现已经从单脚本拆到 `src/` 下：

```text
src/cullary/
  analyzers/
    embedding.py
    face.py
    hash.py
    image_metrics.py
    iqa.py
    media.py
  preprocessing/
    cli.py
    pipeline.py
  constants.py
  domain.py
  features.py
  state.py
  utils.py
scripts/
  verify_phase1_outputs.py   # output contract verifier
  test_phase1_resume.py      # resume/stale contract test
  smoke_phase1.sh            # end-to-end smoke
```

`analyzers` 是 `cullary` 顶层能力模块，不作为 `preprocessing` 的子模块；`preprocessing` 只负责任务编排、状态维护和缓存写入。

## 当前实现状态

Phase 1 的第一版正式 pipeline 已开始落地，入口为：

```text
python -m cullary.preprocessing
cullary-preprocess  # install -e . 后由 pyproject.toml 暴露
```

默认配置为：

```text
config/preprocess.default.json
```

输出验证脚本为：

```text
scripts/verify_phase1_outputs.py
scripts/test_phase1_resume.py
scripts/smoke_phase1.sh
```

当前实现已经覆盖：

- `<input_folder>/.cullary/` 缓存布局。
- `config.snapshot.json`、`task_state.json`、`manifest.jsonl`、`run_summary.json`。
- preview、thumb、analysis、embedding 输出目录。
- metadata、preview、thumb、hash、image_metrics、embedding、face、iqa analyzer。
- analyzer version、config hash、duration、error message、output path。
- 基于 source size/mtime、analyzer version、config hash、output path 的重复运行跳过。
- 前端可轮询的 `task_state.json`。

当前样本验证命令：

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.preprocessing /Users/liubin/Desktop/TestImage
/opt/anaconda3/envs/hippo/bin/python scripts/verify_phase1_outputs.py /Users/liubin/Desktop/TestImage

# 或直接运行 smoke
scripts/smoke_phase1.sh /Users/liubin/Desktop/TestImage
```

CLI 默认输出 text progress；服务端日志可切换为 `--progress jsonl`，后台静默执行可用 `--quiet`。UI 仍以 `.cullary/task_state.json` 作为轮询状态源。

已验证输出：

- 当前本机样本 `manifest.jsonl`：113 条。
- 当前本机样本 `analysis/`：113 个 per-photo analysis。
- 当前本机样本 `previews/`：113 张。
- 当前本机样本 `thumbs/`：113 张。
- 当前本机样本 `embeddings/`：113 个 384 维 DINOv2-small `.npy`。
- `run_summary.status`：`success`。
- `task_state.status`：`success`。
- 重复运行可以命中缓存并跳过已完成 analyzer。
- `scripts/test_phase1_resume.py` 已验证：首次运行全量计算、第二次运行全量 cache hit、删除单张 analysis 后只修复该图片、修改单张图片后只重算该图片相关 analyzer、embedding 模型缺失不会阻塞基础 analyzer、`image_metrics` 配置变化只重算对应 analyzer，并且不会把 `.cullary/` 或 `.cullary_cache/` 下的缓存文件当成源图重复扫描。

## 完成标准

Phase 1 完成时应满足：

- 一个真实 CLI 可以从输入文件夹生成完整 `.cullary/`。
- 任务可中断、可恢复、可跳过未变化结果。
- 所有核心 analyzer 都接入正式 pipeline。
- 输出 schema 足够支撑 Phase 3 聚类和 Phase 4 推荐。
- UI 可以基于 manifest、task_state、thumb、preview 开始构建任务页和图片列表。
