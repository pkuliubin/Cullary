# Phase 0 总结：样本验证与技术预研

Phase 0 目标是验证 Cullary 是否可以在本地稳定读取样本照片、生成 cached preview、产出基础图像指标，并选出第一版可用的轻量模型组合。

当前结论：Phase 0 可以关闭，进入 Phase 1。

## 样本与运行环境

测试样本路径：

```text
/Users/liubin/Desktop/TestImage
```

样本情况：

- 有效照片：46 张。
- `.HEIC`：18 张。
- `.3FR`：28 张。
- 已忽略：`.DS_Store`、`.crdownload`。

主要 Python 环境：

```text
/opt/anaconda3/envs/hippo/bin/python
```

当前缓存目录：

```text
/Users/liubin/Projects/Cullary/.cullary_cache
```

## 已完成验证

### 1. 本地缓存与数据契约

第一版不使用 SQLite，采用：

```text
.cullary_cache/
  previews/
  analysis/
  manifest.jsonl
  run_summary.json
```

已验证：

- `manifest.jsonl` 可一行一张照片记录状态。
- per-photo JSON 可记录 analyzer 输出。
- 重复运行可跳过未变化文件。
- 模型 analyzer 可失败或跳过，不阻塞 metadata / preview / quality。

### 2. Metadata 读取

工具：ExifTool。

结果：

- 46/46 metadata 读取成功。
- 可获取文件类型、尺寸、拍摄时间、相机、镜头、曝光参数等基础字段。

### 3. Preview 提取

已验证路径：

- `.HEIC`：ExifTool `PreviewImage` 成功。
- `.3FR`：IFD0 byte-slice 成功。

`.3FR` 关键结论：

- 当前样本可以通过 ExifTool 读取 IFD0 `StripOffsets` / `StripByteCounts`。
- 从源文件按 byte slice 读取后可得到有效 JPEG preview。
- 无需第一版默认解 full RAW。

暂不阻塞项：

- JPG/JPEG 样本验证后续再补。
- HEIC/RAW fallback 后续再补。
- color profile / orientation 细节后续继续校验。

### 4. 基础图像指标

测试脚本：

```text
scripts/benchmark_image_metrics.py
```

输出：

```text
.cullary_cache/image_metrics_probe.json
```

已验证：

- 46/46 成功。
- 默认缩到长边 1024 计算。
- 平均耗时约 168.84ms/张。

已测试数据大类：

- 亮度与曝光：`brightness_mean`、`shadow_clip_ratio`、`highlight_clip_ratio`、`dynamic_range_p05_p95`。
- 色彩统计：`saturation_mean`、`color_cast_strength`、`white_balance_deviation`。
- 清晰度：`laplacian_var`、`tenengrad`、`edge_density`、`center_laplacian_var`。
- 模糊 proxy：`gradient_anisotropy`、`dominant_angle_deg`。
- 简单构图：`aspect_ratio`、`orientation`、`center_brightness_delta`、`center_sharpness_ratio`。

结论：非模型图像指标应作为第一版推荐排序的基础数据。

### 5. Embedding 模型

测试脚本：

```text
scripts/benchmark_embedding_models.py
```

输出：

```text
.cullary_cache/embedding_benchmark.json
```

已测试模型：

| 模型 | 状态 | 输出维度 | 参数量 | 热身后平均 | 结论 |
|---|---:|---:|---:|---:|---|
| DINOv2-small | 成功 | 384 | 22.1M | 约 172ms | 第一版默认 |
| CLIP ViT-B/32 | 成功 | 512 | 151.3M | 约 163ms | 语义对照 |
| DINOv2-base | 成功 | 768 | 86.6M | 约 408ms | 质量对照 |
| SigLIP base vision | 成功 | 768 | 92.9M | 约 239ms | 语义对照 |

结论：第一版默认 `DINOv2-small` 作为 `visual_embedding`。

### 6. Face 模型

已测试模型：OpenCV YuNet。

模型文件：

```text
.cullary_cache/models/yunet/face_detection_yunet_2023mar.onnx
```

输出：

```text
.cullary_cache/face_yunet_test.json
.cullary_cache/face_yunet_metrics.json
.cullary_cache/face_yunet_overlays/
.cullary_cache/face_yunet_metric_overlays/
```

结果：

- 46/46 处理成功。
- 12 张检测到人脸。
- 共检测到 17 张人脸。
- 可输出 `box`、`score`、5 点 `landmarks`、`area_ratio`、`eye_distance`、`face_sharpness`、`alignment_score`。

结论：第一版默认 `OpenCV YuNet` 作为 face analyzer。

MediaPipe / InsightFace 状态：

- MediaPipe 包已安装，但当前是 tasks API，需要额外 `.tflite` 模型后再测。
- InsightFace 包已安装，但缺少 `buffalo_l` 等模型权重，后续如需 face embedding / 同人聚类再测。

### 7. IQA 指标

测试脚本：

```text
scripts/benchmark_iqa_models.py
```

输出：

```text
.cullary_cache/iqa_benchmark.json
.cullary_cache/iqa_benchmark_brisque_niqe.json
```

已测试：

- `PIQE`
- `BRISQUE`
- `NIQE`
- `NRQM`

关键结论：

- IQA 指标对输入尺寸非常敏感。
- 直接跑大 preview 很慢。
- 缩到 512 或 1024 后，PIQE / NIQE / BRISQUE 可用。
- NRQM 更适合图像恢复/增强质量评估，不适合作为第一版照片 culling 默认路径。

第一版建议：

```text
默认或可选：PIQE@512
对照：NIQE@512 / BRISQUE@512
不默认：NRQM
```

## 第一版默认配置建议

```json
{
  "image_metrics": {
    "max_side": 1024
  },
  "embedding": {
    "default_model": "dinov2-small",
    "input_size": "processor_default"
  },
  "face": {
    "default_model": "yunet",
    "max_side": 1280,
    "score_threshold": 0.6
  },
  "iqa": {
    "default_metric": "piqe",
    "max_side": 512,
    "compare_metrics": ["niqe", "brisque"]
  }
}
```

## 第一版应建设的数据维度

### Source / Metadata

- source path / extension / size / mtime。
- EXIF metadata：拍摄时间、相机、镜头、焦距、快门、光圈、ISO、方向。

### Preview

- cached JPEG preview path。
- preview method。
- preview width / height。

### Image Metrics

- 曝光与亮度。
- 色彩与白平衡 proxy。
- 清晰度与模糊 proxy。
- 简单构图 proxy。

### Hash

- aHash。
- dHash。
- pHash 后续可补。

### Visual Embedding

- model name / version。
- embedding dim。
- embedding path。
- input size。

### Face Metrics

- face count。
- boxes。
- landmarks。
- face area ratio。
- face sharpness。
- alignment proxy。

### IQA

- PIQE / NIQE / BRISQUE 原始分数。
- 固定 input size。
- 统一方向后的 normalized IQA score 后续再定。

### 后续 Phase 1/2 数据

- cluster id。
- recommendation score。
- recommendation reason。
- user decision。
- file operation log。

## Phase 0 关闭条件对照

| 条件 | 状态 |
|---|---:|
| 能扫描样本目录 | 完成 |
| 能读取 metadata | 完成 |
| 能生成 cached preview | 完成 |
| `.3FR` preview 有可行路径 | 完成 |
| `.HEIC` preview 有可行路径 | 完成 |
| 基础图像指标可计算 | 完成 |
| embedding 模型有默认选择 | 完成 |
| face 模型有默认选择 | 完成 |
| IQA 策略有默认选择 | 完成 |
| 数据维度已整理 | 完成 |

## 不阻塞 Phase 0 的后续项

- JPG/JPEG 样本补测。
- preview fallback 补测。
- rawpy / pillow_heif fallback。
- MediaPipe / InsightFace 对照测试。
- MPS 环境优化。
- 大规模批量性能基准。
- UI 端完整工作流。

## 下一阶段

进入 Phase 1：Analysis Schema and Local Cache。

优先任务：

1. 增加 preprocess 配置文件。
2. 将 `image_metrics` 接入正式 analyzer。
3. 将 `DINOv2-small` embedding 接入正式 analyzer。
4. 将 `YuNet` face metrics 接入正式 analyzer。
5. 将 `PIQE@512` 接入正式 analyzer，作为可选 IQA。
6. 固化 per-photo analysis JSON 数据契约。
