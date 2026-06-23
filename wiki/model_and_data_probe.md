# 模型与数据维度预研记录

本文记录 Cullary 预处理阶段已经明确跑过的本地库、模型、测试结果，以及第一版需要建设的数据维度。

当前样本路径：

```text
/Users/liubin/Desktop/TestImage
```

当前缓存路径：

```text
/Users/liubin/Projects/Cullary/.cullary_cache
```

## 当前阶段目标

预处理阶段的核心目标不是直接做最终推荐，而是为后续聚类、组内排序、推荐解释和 UI 审核建立稳定的数据基础。

第一版要做到：

- 不改动源文件。
- 为每张照片生成可复用的 cached JPEG preview。
- 为每张照片生成稳定 JSON analysis record。
- 产出足够支撑“相似照片聚类 + 组内选优”的基础特征。
- 模型失败不阻塞基础 metadata / preview / quality 输出。

## 已测试的基础能力

### ExifTool

状态：已测试通过。

用途：

- 读取 metadata。
- 提取 HEIC embedded preview。
- 读取 `.3FR` IFD0 preview 相关字段。

样本结果：

- 46 张照片 metadata 全部成功。
- HEIC 可以通过 `PreviewImage` 得到 cached JPEG preview。
- `.3FR` 可以通过 IFD0 byte-slice 得到 JPEG preview。

### macOS sips

状态：已验证可作为 HEIC/JPEG fallback 路径。

用途：

- 当 ExifTool preview 失败时，将可解码图片转成 JPEG preview。

当前样本里 HEIC 已通过 ExifTool 成功，因此 `sips` 不是主路径。

### Pillow / NumPy / OpenCV

状态：已测试通过。

用途：

- 读取 cached preview。
- 计算 aHash / dHash。
- 计算基础质量指标。
- 画 face overlay 图。
- OpenCV YuNet face detection。

已产出：

- `hash.json`
- `quality.json`
- face detection JSON
- face overlay 图片

## 已测试的 embedding 模型

这些模型都用于产出 `visual_embedding`。主要用途是相似照片聚类，也可辅助近重复判断、语义筛选和后续推荐排序。

测试脚本：

```text
/Users/liubin/Projects/Cullary/scripts/benchmark_embedding_models.py
```

输出文件：

```text
/Users/liubin/Projects/Cullary/.cullary_cache/embedding_benchmark.json
```

测试图片：

```text
/Users/liubin/Desktop/TestImage/B0007796.HEIC
```

| 模型 | 状态 | 输出维度 | 参数量 | 首次推理 | 热身后平均 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| CLIP ViT-B/32 | 成功 | 512 | 151.3M | 529ms | 163ms | 适合作为语义 embedding 对照 |
| DINOv2 small | 成功 | 384 | 22.1M | 333ms | 172ms | 适合作为第一版默认 visual embedding |
| DINOv2 base | 成功 | 768 | 86.6M | 818ms | 408ms | 可作为质量对照，不建议默认全量 |
| SigLIP base vision | 成功 | 768 | 92.9M | 841ms | 239ms | 可作为语义 embedding 对照 |

当前建议：

```text
默认：DINOv2-small
对照：CLIP ViT-B/32
暂不默认：DINOv2-base / SigLIP base
```

说明：当前测试运行在 CPU。当前 `hippo` 环境中 PyTorch 的 MPS 检测异常，后续可以单独优化 MPS 环境。

## 已测试的 face 模型

### OpenCV YuNet

状态：已测试通过。

模型文件：

```text
/Users/liubin/Projects/Cullary/.cullary_cache/models/yunet/face_detection_yunet_2023mar.onnx
```

测试输出：

```text
/Users/liubin/Projects/Cullary/.cullary_cache/face_yunet_test.json
/Users/liubin/Projects/Cullary/.cullary_cache/face_yunet_metrics.json
/Users/liubin/Projects/Cullary/.cullary_cache/face_yunet_overlays
/Users/liubin/Projects/Cullary/.cullary_cache/face_yunet_metric_overlays
```

测试结果：

- 46 张 cached previews 全部处理成功。
- 12 张检测到人脸。
- 共检测到 17 张人脸。
- 可输出 box、score、5 点 landmarks、面积比例、眼距、清晰度 proxy、对齐 proxy。

当前已验证可生成的数据结构：

```json
{
  "face_count": 2,
  "largest_face_area_ratio": 0.009571,
  "faces": [
    {
      "box": {"x": 1559.2, "y": 1206.0, "w": 270.0, "h": 402.1},
      "score": 0.9056,
      "area_ratio": 0.009571,
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
```

当前建议：

```text
第一版默认 face analyzer：YuNet
```

注意：当前 benchmark 直接使用大 preview，速度偏慢。实际 analyzer 应先缩放到固定长边，例如 960 或 1280，再把坐标映射回 preview 坐标。

### MediaPipe

状态：包已安装，但未完成 benchmark。

已确认：

- `mediapipe 0.10.35` 可 import。
- 当前安装版本是 tasks API，不包含旧的 `mp.solutions.face_detection`。
- 本地没有 MediaPipe face detector `.tflite` 模型文件。

结论：需要额外下载 `.tflite` task 模型后再测。

### InsightFace

状态：包已安装，但未完成 benchmark。

已确认：

- `insightface 1.0.1` 可 import。
- `onnxruntime 1.27.0` 可 import。
- 本地缺少 `buffalo_l` 等 InsightFace 模型权重。
- 默认模型路径写入 `~/.insightface`，当前没有作为项目 cache 路径跑通。

结论：暂不纳入第一版默认。后续如果要做 face embedding / 同人聚类，可以把 InsightFace 模型下载到 `.cullary_cache/models/insightface` 后单独测试。

## 已测试的 IQA 指标

测试脚本：

```text
/Users/liubin/Projects/Cullary/scripts/benchmark_iqa_models.py
```

输出文件：

```text
/Users/liubin/Projects/Cullary/.cullary_cache/iqa_benchmark.json
/Users/liubin/Projects/Cullary/.cullary_cache/iqa_benchmark_brisque_niqe.json
```

已测试指标：

| 指标 | 状态 | 输出 | 分数方向 | 结论 |
|---|---:|---|---|---|
| PIQE | 成功 | 单个质量分数 | 越低越好 | 缩图后可用，适合作为轻量候选 |
| BRISQUE | 成功 | 单个质量分数 | 越低越好 | 缩图后可用，但分数需归一化 |
| NIQE | 成功 | 单个质量分数 | 越低越好 | 缩图后可用，可作为对照 |
| NRQM | 下载权重成功，但计算太慢 | 单个自然度分数 | 通常越高越好 | 不适合第一版照片 culling 默认路径 |

分辨率影响非常明显。同一张图缩放测试结果：

| 输入尺寸 | PIQE | NIQE | BRISQUE |
|---|---:|---:|---:|
| 原图 3888x2918 | 1417ms | 4698ms | 2789ms |
| 512x384 | 69ms | 151ms | 100ms |
| 1024x769 | 154ms | 261ms | 364ms |
| 1600x1201 | 243ms | 696ms | 312ms |

当前建议：

```text
默认质量路径：传统质量 proxy + 可选 PIQE@512
对照指标：NIQE@512 / BRISQUE@512
不默认：NRQM
```

说明：IQA 指标应该固定输入尺寸，否则不同照片之间分数不可比。

## 当前阶段需要建设的数据维度

### 1. Source File 数据

用途：定位源文件、做增量扫描、最终安全移动文件。

来源：文件系统 stat + 扫描器。

字段建议：

- `source_id`
- `path`
- `extension`
- `size`
- `mtime_ns`
- `inode` 可选
- `scan_status`

### 2. Metadata 数据

用途：时间分组、设备信息、曝光参数解释、UI 展示。

来源：ExifTool。

字段建议：

- `file_type`
- `mime_type`
- `image_width`
- `image_height`
- `date_time_original`
- `create_date`
- `make`
- `model`
- `lens_model`
- `focal_length`
- `exposure_time`
- `f_number`
- `iso`
- `orientation`
- `gps` 可选

### 3. Preview / Thumbnail 数据

用途：后续所有视觉分析和 UI 展示都基于 cache，不直接碰源文件。

来源：ExifTool preview、`.3FR` IFD0 byte-slice、`sips` fallback、Pillow/OpenCV thumbnail。

字段建议：

- `preview_path`
- `preview_width`
- `preview_height`
- `preview_method`
- `thumbnail_paths`
- `orientation_applied`
- `color_profile_status`

### 4. Perceptual Hash 数据

用途：近重复、连拍相似辅助、快速预聚类。

来源：Pillow + NumPy。

字段建议：

- `ahash`
- `dhash`
- `phash` 后续可补
- `hash_version`

### 5. Visual Embedding 数据

用途：视觉相似聚类，是 cluster 的核心输入之一。

来源：DINOv2-small 默认；CLIP/SigLIP 可作为对照。

字段建议：

- `model_name`
- `model_version`
- `embedding_dim`
- `embedding_path`
- `embedding_norm`
- `input_size`
- `duration_ms`

第一版默认：

```text
DINOv2-small visual_embedding
```

### 6. 非模型图像指标数据

用途：在不依赖模型的情况下，评估照片的亮度、曝光、对比度、色彩、清晰度、模糊风险和简单构图。这类数据稳定、可解释，应该作为第一版推荐排序的基础。

来源：cached JPEG preview + OpenCV / NumPy。当前测试脚本为：

```text
/Users/liubin/Projects/Cullary/scripts/benchmark_image_metrics.py
```

当前测试输出：

```text
/Users/liubin/Projects/Cullary/.cullary_cache/image_metrics_probe.json
```

当前测试策略：

- 只读取 cached preview，不碰源文件。
- 默认将 preview 缩放到长边 `1024` 后计算。
- 保留原 preview 尺寸和实际分析尺寸。
- 46 张样本全部成功。
- 平均耗时约 `168.84ms/张`。

建议正式 analyzer 名称：

```text
image_metrics
```

#### 6.1 输入尺寸数据

用途：记录指标是在什么尺寸下计算的，保证后续可比性。

字段：

- `source_size.width`
- `source_size.height`
- `analysis_size.width`
- `analysis_size.height`
- `analysis_size.scale`

当前计算方式：

```text
scale = min(1.0, max_side / max(source_width, source_height))
analysis_width = int(source_width * scale)
analysis_height = int(source_height * scale)
```

第一版建议：

```text
image_metrics.max_side = 1024
```

#### 6.2 亮度与曝光统计

用途：判断整体偏暗、偏亮、死黑、死白、动态范围不足等问题。

输入：分析尺寸下的灰度图 `gray`，像素范围 `0-255`。

字段定义：

- `brightness_mean`
  - 灰度平均值。
  - 计算：`mean(gray)`。
  - 含义：整体亮度粗略估计。

- `brightness_median`
  - 灰度中位数。
  - 计算：`percentile(gray, 50)`。
  - 含义：比平均值更抗极端高光/阴影。

- `brightness_p01 / brightness_p05 / brightness_p95 / brightness_p99`
  - 灰度分位数。
  - 计算：`percentile(gray, [1, 5, 95, 99])`。
  - 含义：描述暗部和亮部边界。

- `shadow_clip_ratio`
  - 接近纯黑像素比例。
  - 当前计算：`count(gray <= 4) / pixel_count`。
  - 含义：死黑或严重欠曝风险。

- `highlight_clip_ratio`
  - 接近纯白像素比例。
  - 当前计算：`count(gray >= 251) / pixel_count`。
  - 含义：死白或严重过曝风险。

- `contrast_std_ratio`
  - 灰度标准差归一化。
  - 当前计算：`std(gray) / 255.0`。
  - 含义：整体对比度 proxy。

- `dynamic_range_p05_p95`
  - 排除极端像素后的动态范围 proxy。
  - 当前计算：`(p95(gray) - p05(gray)) / 255.0`。
  - 含义：比 max-min 更稳，适合判断画面层次。

#### 6.3 色彩统计

用途：判断饱和度、偏色、白平衡偏移等问题。

输入：分析尺寸下的 RGB 图和 HSV 图。

字段定义：

- `saturation_mean`
  - HSV S 通道均值。
  - 当前计算：`mean(hsv.saturation) / 255.0`。
  - 含义：整体饱和度。

- `saturation_median`
  - HSV S 通道中位数。
  - 当前计算：`median(hsv.saturation) / 255.0`。
  - 含义：比均值更抗局部高饱和区域。

- `saturation_clip_ratio`
  - 接近满饱和像素比例。
  - 当前计算：`count(saturation >= 250) / pixel_count`。
  - 含义：过饱和风险。

- `value_mean`
  - HSV V 通道均值。
  - 当前计算：`mean(hsv.value) / 255.0`。
  - 含义：HSV 视角下的明度。

- `rgb_mean`
  - RGB 三通道均值。
  - 当前计算：`mean(rgb.reshape(-1, 3), axis=0)`。
  - 含义：整体色彩分布。

- `color_cast_rgb_deviation`
  - RGB 均值相对三通道整体均值的偏移。
  - 当前计算：`rgb_mean - mean(rgb_mean)`。
  - 含义：粗略判断偏红、偏绿、偏蓝。

- `color_cast_strength`
  - RGB 偏移强度。
  - 当前计算：`norm(color_cast_rgb_deviation) / 255.0`。
  - 含义：偏色强度 proxy。

- `white_balance_deviation`
  - 灰世界假设下的白平衡偏差。
  - 当前计算：`(max(rgb_mean) - min(rgb_mean)) / mean(rgb_mean)`。
  - 含义：白平衡偏移 proxy。

#### 6.4 噪声 proxy

用途：粗略估计平坦区域的高频残差，作为噪声风险参考。

字段：

- `noise_proxy`

当前计算方式：

```text
blur = GaussianBlur(gray, 5x5)
residual = gray - blur
grad = sqrt(SobelX(gray)^2 + SobelY(gray)^2)
mask = grad <= percentile(grad, 30)
noise_proxy = std(residual[mask]) / 255.0
```

含义：

- 只在低梯度区域估计高频残差，避免把真实边缘当噪声。
- 当前只是 proxy，需要更多样本校准。
- 第一版可以保留字段，但不建议直接强参与推荐排序。

#### 6.5 清晰度与模糊指标

用途：识别糊片、失焦、低细节照片，是 culling 的核心数据之一。

输入：分析尺寸下的灰度图。

字段定义：

- `laplacian_var`
  - Laplacian 方差。
  - 当前计算：`var(Laplacian(gray))`。
  - 含义：经典清晰度 proxy，越高通常越清晰。

- `tenengrad`
  - Sobel 梯度能量均值。
  - 当前计算：`mean(SobelX(gray)^2 + SobelY(gray)^2)`。
  - 含义：边缘/细节强度，越高通常越清晰。

- `edge_density`
  - Canny 边缘像素比例。
  - 当前计算：
    ```text
    median = median(gray)
    lower = max(0, 0.66 * median)
    upper = min(255, 1.33 * median)
    edge_density = count(Canny(gray, lower, upper) > 0) / pixel_count
    ```
  - 含义：画面边缘密度，可辅助判断细节丰富度。

- `center_laplacian_var`
  - 中心区域 Laplacian 方差。
  - 当前中心区域：图像中间 50% 宽高，即 `[25%, 75%]`。
  - 含义：主体常在中心附近时，比全图清晰度更有参考。

- `center_tenengrad`
  - 中心区域 Tenengrad。
  - 当前计算：对中心区域重复 Sobel 梯度能量计算。

- `center_sharpness_ratio`
  - 中心清晰度相对全图清晰度。
  - 当前计算：`(center_laplacian_var + 1e-6) / (laplacian_var + 1e-6)`。
  - 含义：中心是否比全图更清晰。

#### 6.6 运动模糊 proxy

用途：粗略识别方向性模糊风险。

字段：

- `gradient_anisotropy`
- `dominant_angle_deg`

当前计算方式：

```text
Gx = SobelX(gray)
Gy = SobelY(gray)
gxx = mean(Gx * Gx)
gyy = mean(Gy * Gy)
gxy = mean(Gx * Gy)
trace = gxx + gyy
discr = sqrt((gxx - gyy)^2 + 4 * gxy^2)
lambda1 = (trace + discr) / 2
lambda2 = (trace - discr) / 2
gradient_anisotropy = (lambda1 - lambda2) / (lambda1 + lambda2)
dominant_angle_deg = 0.5 * atan2(2 * gxy, gxx - gyy)
```

含义：

- `gradient_anisotropy` 越高，梯度方向越集中。
- 方向性强可能来自运动模糊，也可能来自建筑线条、水平地平线等正常结构。
- 第一版建议保留字段，但不要单独作为删片依据。

#### 6.7 简单构图数据

用途：为后续推荐解释提供基础构图信息。第一版不做复杂主体检测。

字段定义：

- `aspect_ratio`
  - 原 preview 宽高比。
  - 当前计算：`source_width / source_height`。

- `orientation`
  - 简单方向分类。
  - 当前规则：
    ```text
    if width > height * 1.1: landscape
    elif height > width * 1.1: portrait
    else: squareish
    ```

- `center_brightness_mean`
  - 中心区域灰度均值。
  - 中心区域同样使用中间 50% 宽高。

- `center_brightness_delta`
  - 中心区域亮度与全图亮度差。
  - 当前计算：`mean(center_gray) - mean(gray)`。
  - 含义：中心主体是否更亮或更暗。

- `rule_of_thirds_points_norm`
  - 三分线交点，当前是固定归一化坐标。
  - 当前输出：
    ```json
    [[0.3333, 0.3333], [0.6667, 0.3333], [0.3333, 0.6667], [0.6667, 0.6667]]
    ```
  - 含义：后续可结合 face center / subject center 计算距离。

#### 6.8 第一版字段使用建议

第一版正式写入 JSON 的字段可以全部保留，但推荐排序先使用更稳定的核心字段。

建议参与推荐或解释的字段：

- `brightness_mean`
- `shadow_clip_ratio`
- `highlight_clip_ratio`
- `contrast_std_ratio`
- `dynamic_range_p05_p95`
- `saturation_mean`
- `color_cast_strength`
- `white_balance_deviation`
- `laplacian_var`
- `tenengrad`
- `edge_density`
- `center_laplacian_var`
- `center_sharpness_ratio`
- `aspect_ratio`
- `orientation`

建议先保留但不强参与推荐的实验字段：

- `noise_proxy`
- `gradient_anisotropy`
- `dominant_angle_deg`

### 7. Face Metrics 数据

用途：人像照片组内排序，解释“人脸更清晰/主体更大/表情更可用”。

来源：OpenCV YuNet + OpenCV crop sharpness。

字段建议：

- `face_count`
- `largest_face_area_ratio`
- `faces[].box`
- `faces[].score`
- `faces[].area_ratio`
- `faces[].center`
- `faces[].landmarks`
- `faces[].eye_distance`
- `faces[].eye_angle_deg`
- `faces[].alignment_score`
- `faces[].sharpness_laplacian_var`

暂不做默认：

- 闭眼判断
- 表情识别
- face embedding
- 同人聚类

### 8. IQA 数据

用途：补充传统质量指标，辅助推荐排序。

来源：pyiqa PIQE / NIQE / BRISQUE，固定缩放尺寸。

字段建议：

- `iqa_input_size`
- `piqe_score`
- `niqe_score`
- `brisque_score`
- `score_direction`
- `normalized_iqa_score`

第一版建议：

```text
保留原始分数；另算统一 0-1、越高越好的 normalized_iqa_score。
```

### 9. Cluster 数据

用途：将相似照片组织成可审核单元。

来源：visual embedding + perceptual hash + metadata time window。

字段建议：

- `cluster_id`
- `source_ids`
- `cluster_method`
- `distance_threshold`
- `representative_source_id`
- `near_duplicate_pairs`
- `created_at`

### 10. Recommendation 数据

用途：给 UI 展示推荐保留项和原因。

来源：综合质量指标、face metrics、IQA、cluster 内相对排序。

字段建议：

- `recommendation_score`
- `recommendation_rank`
- `recommendation_action`: `keep | reject | review`
- `recommendation_reason`
- `score_breakdown`

推荐解释应该尽量可读，例如：

```text
同组中人脸最大且更清晰，曝光正常，构图相似。
```

### 11. User Decision / File Operation 数据

用途：保证用户决策可追踪、文件操作可恢复。

来源：UI 人工确认 + 文件操作层。

字段建议：

- `user_decision`
- `decision_time`
- `target_path`
- `operation_status`
- `operation_log_path`
- `rollback_available`

## 当前第一版默认组合

```text
metadata: ExifTool
preview: ExifTool / .3FR IFD0 byte-slice / sips fallback
hash: aHash + dHash
visual_embedding: DINOv2-small
face: OpenCV YuNet
quality: traditional proxy
IQA: PIQE@512 可选，NIQE@512 / BRISQUE@512 对照
cluster: embedding + hash + time window
recommendation: quality + face + IQA + cluster-relative ranking
```

## 尚未完成但可后续测试

- MediaPipe FaceDetector `.tflite` task 模型。
- InsightFace `buffalo_l` 模型和 face embedding。
- `rawpy` RAW fallback。
- `pillow_heif` HEIC decode fallback。
- MobileCLIP / OpenCLIP。
- MUSIQ / MANIQA / TOPIQ / CLIPIQA / NIMA 等重 IQA 或审美模型。
