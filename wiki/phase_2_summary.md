# Phase 2 总结：Review Set + 多 embedding 聚类管线

本阶段完成了 Cullary 从单图预处理结果到前端可直接渲染 review model 的核心链路。当前正式入口会完整执行：

```text
Phase 1 preprocessing
  -> Phase 2 review set generation / clustering
  -> .cullary/review_sets.jsonl
  -> .cullary/review_summary.json
```

正式命令：

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.pipeline \
  /path/to/photo-folder \
  --progress jsonl
```

测试目录：

```text
/Users/liubin/Desktop/TestImage
```

## 当前阶段结论

当前 Phase 1 + Phase 2 数据管线已经可以交付给前端第一版 review UI 使用。

前端主要消费：

```text
<input_folder>/.cullary/review_summary.json
<input_folder>/.cullary/review_sets.jsonl
```

这两个文件已经包含 review UI 所需的 review set、primary keeper、alternate keeper、cluster 级 challenger queue、图片路径、图片尺寸、评分、排序和结构化中文解释。

## Phase 1 计算顺序

本阶段调整了 Phase 1 的计算顺序，使人物分割和多 embedding 能正确依赖前置结果。

当前顺序：

```text
scan
metadata
preview
thumb
hash
face
person_mask
image_metrics
embedding
iqa
```

关键依赖：

```text
face -> person_mask
person_mask -> image_metrics
person_mask -> embedding
```

原因：

- `person_mask` 只在 `face_count > 0` 时运行。
- `foreground_area_ratio` 来自 person mask，需要写入 image metrics。
- embedding 阶段支持 batch，因此整图、前景、背景 embedding 放在同一阶段批量计算。

## Phase 1 新增能力

### Person Mask

如果 YuNet 检测到人脸，pipeline 会继续运行 MediaPipe selfie segmentation：

```text
preview
  -> MediaPipe selfie_segmenter.tflite
  -> person mask
  -> enhanced person mask
  -> foreground image
  -> background fill image
```

模型路径：

```text
/Users/liubin/.cullary/models/mediapipe/selfie_segmenter.tflite
```

生成文件：

```text
.cullary/masks/<display_id>__person.png
.cullary/masks/<display_id>__person_enhanced.png
.cullary/foregrounds/<display_id>.jpg
.cullary/backgrounds/<display_id>.jpg
```

如果没有检测到人脸：

```json
{
  "person_mask": {
    "reason": "no_face_detected"
  },
  "foreground_embedding": null,
  "background_embedding": null
}
```

### Enhanced Background Fill

背景图使用 enhanced blur fill，而不是简单灰色填充或 inpainting。

处理方式：

```text
person mask
  -> dilate
  -> feather
  -> 低分辨率大半径 blur
  -> resize 回 preview 尺寸
  -> 用增强 mask composite 到原图
```

当前默认配置：

```json
{
  "dilate_px": 32,
  "feather_px": 18,
  "enhanced_blur_radius": 120
}
```

这个方式的目标不是生成真实背景，而是削弱人物区域对 background embedding 的影响，同时避免黑块/灰块这类强伪影。

### 三路 Embedding

每张图固定有：

```text
global_embedding
```

有人脸且 person mask 成功时额外有：

```text
foreground_embedding
background_embedding
```

生成文件：

```text
.cullary/embeddings/<display_id>.npy
.cullary/foreground_embeddings/<display_id>.npy
.cullary/background_embeddings/<display_id>.npy
```

analysis JSON 中对应字段：

```text
embedding
foreground_embedding
background_embedding
```

当前 embedding analyzer 使用 `device=auto`：优先 Torch MPS，MPS 不可用时回退到 CPU。保守默认值为 MPS `batch_size=4`、CPU `batch_size=8`。

### 前景占比

`foreground_area_ratio` 来自 person mask 原始覆盖面积。

写入位置：

```text
analysis.image_metrics.foreground.foreground_area_ratio
analysis.person_mask.foreground_area_ratio
manifest.ui_summary.foreground_area_ratio
```

它可以用于后续判断：

```text
人物是否是强主体
背景 embedding 的可信程度
前景相似度是否应该参与 veto
```

## Phase 2 聚类策略

当前 clustering 不再使用简单的 120 秒硬切分，而是：

```text
按拍摄时间排序
  -> hard break 分段
  -> 时间窗口内候选比较
  -> embedding similarity 建图
  -> connected components
  -> review set
```

hard break 包括：

```text
日期变化
超大时间间隔
相机设备变化
```

当前配置：

```json
{
  "candidate_time_window_seconds": 1800,
  "candidate_neighbor_limit": 40,
  "hard_time_gap_seconds": 3600,
  "embedding_similarity_threshold": 0.86,
  "near_duplicate_similarity_threshold": 0.93
}
```

## 多 Embedding Edge Decision

如果两张图都有 foreground/background embedding，则使用三路相似度：

```text
global_sim
foreground_sim
background_sim
```

当前 combined similarity：

```text
combined_sim =
  0.45 * global_sim +
  0.30 * background_sim +
  0.25 * foreground_sim
```

默认配置：

```json
{
  "multi_embedding": {
    "enabled": true,
    "combined_similarity_threshold": 0.84,
    "global_weight": 0.45,
    "background_weight": 0.30,
    "foreground_weight": 0.25,
    "background_veto_threshold": 0.60,
    "foreground_veto_threshold": 0.50,
    "foreground_veto_min_area_ratio": 0.08,
    "mixed_foreground_global_threshold": 0.90
  }
}
```

规则：

```text
两张都有前景/背景 embedding:
  使用 combined_sim，并应用 background / foreground veto

一张有前景/背景 embedding，另一张没有:
  提高 global threshold 到 0.90

两张都没有前景/背景 embedding:
  使用 global_sim >= 0.86
```

这样可以更好地区分：

```text
同背景不同人
同人不同背景
人像与纯风景混合场景
```

## Phase 2 输出

### review_summary.json

任务概览文件。前端可用于完成页、统计卡片和加载入口。

包含：

```text
status
total_photos
review_set_count
single_count
near_duplicate_count
similar_scene_count
recommended_keep_count
alternate_keeper_count
keeper_slot_count
challenger_count
cache_hit
input_hash
config_hash
failures
```

### review_sets.jsonl

核心 review model。一行一个 review set / cluster。

每行包含：

```text
schema_version
review_set_id
set_type
photo_count
cover_display_id
primary_keeper_id
recommended_keep_ids[]
alternate_keeper_ids[]
alternate_keeper_count
challenger_queue[]
keeper_slots[]  # compatibility only
photos[]
reason_summary_zh[]
```

`challenger_queue[]` 是 cluster 级队列，包含所有非 primary 照片：

```text
photo_id
rank
compare_to
is_alternate_keeper
similarity_to_primary
score_delta
reason_zh
```

`keeper_slots[]` 仍保留给旧 UI 过渡使用，但不再是主合约。

`photos[]` 包含：

```text
display_id
source_id
source_path
thumb_path
thumb_width
thumb_height
preview_path
preview_width
preview_height
analysis_path
rank
recommendation
ui_initial_state
score
badges
warnings
reason_summary_zh[]
weakness_summary_zh[]
foreground_area_ratio
has_foreground_embedding
has_background_embedding
```

前端不需要自己推断推荐关系；应优先读取 `primary_keeper_id`、`alternate_keeper_ids` 和顶层 `challenger_queue`。

## TestImage 验收结果

测试目录：

```text
/Users/liubin/Desktop/TestImage
```

完整执行命令：

```bash
PYTHONPATH=src /opt/anaconda3/envs/hippo/bin/python -m cullary.pipeline \
  /Users/liubin/Desktop/TestImage \
  --progress jsonl \
  --force
```

Phase 1 结果：

```text
total_photos: 113
status: success
embedding success: 113
person_mask success: 39
person_mask skipped: 74
foreground_embeddings: 39
background_embeddings: 39
```

Phase 2 结果：

```text
review_set_count: 38
single_count: 21
near_duplicate_count: 5
similar_scene_count: 12
recommended_keep_count: 38
alternate_keeper_count: 9
keeper_slot_count: 38
challenger_count: 75
lower_ranked_count: 23
```

cluster 大小分布：

```text
1 张:  21 个
2 张:   4 个
3 张:   5 个
4 张:   2 个
5 张:   2 个
6 张:   1 个
7 张:   1 个
8 张:   1 个
30 张:  1 个
```

clustering debug：

```text
clustering_method: time_window_candidate_graph_connected_components
hard_segment_count: 6
compared_pairs: 1011
accepted_edges: 425
```

## 验证方式

### Schema / Contract 验证

```bash
/opt/anaconda3/envs/hippo/bin/python scripts/verify_phase2_outputs.py \
  /Users/liubin/Desktop/TestImage
```

验证内容：

```text
所有 Phase 1 成功图片都进入且只进入一个 review set
review_summary 统计和 review_sets 一致
recommended_keep_ids 只包含 primary keeper
alternate_keeper_ids 只包含非 primary 照片
多图 set 的顶层 challenger_queue 包含所有非 primary 照片
兼容 keeper_slots 指向 primary keeper
thumb / preview / analysis / source 路径存在
图片尺寸存在且为正数
score 为 0-1 有限值
recommendation -> ui_initial_state 映射正确
reason_summary_zh / weakness_summary_zh 为数组
```

### 静态检查

```bash
/opt/anaconda3/envs/hippo/bin/python -m py_compile \
  $(find src/cullary -path '*/__pycache__' -prune -o -name '*.py' -print | sort) \
  scripts/verify_phase2_outputs.py \
  scripts/benchmark_mediapipe_segmentation.py

git diff --check

/opt/anaconda3/envs/hippo/bin/python -m json.tool config/preprocess.default.json >/tmp/cullary_config_check.json
```

### 人工 Cluster Review 导出

为了人工检查 cluster 是否合理，可以导出按 set 分组的 preview：

```bash
/opt/anaconda3/envs/hippo/bin/python scripts/export_cluster_review.py \
  /Users/liubin/Desktop/TestImage \
  --clean

open /Users/liubin/Desktop/TestImage/.cullary/cluster_review
```

导出结构：

```text
cluster_review/
  index.json
  set_000001__similar_scene__004_photos/
    01__KEEP__B0007060_3FR.jpg
    02__KEEP__B0007062_3FR.jpg
    03__ALT__B0007059_3FR.jpg
    set_manifest.json
```

## JSONL Progress Contract

`--progress jsonl` 模式下，stdout 只输出 JSONL event。

示例：

```jsonl
{"type":"progress","stage":"scan","done":113,"total":113,"message":"Scan complete"}
{"type":"progress","stage":"review_sets","done":38,"total":38,"message":"Review sets generated"}
{"type":"completed","summary_path":".cullary/review_summary.json","review_sets_path":".cullary/review_sets.jsonl"}
```

第三方库日志会被重定向到 stderr，避免污染 stdout JSONL。

Tauri/Rust 集成建议：

```text
读取 Python stdout
逐行 JSON.parse
转发为 pipeline-progress / pipeline-completed / pipeline-failed
stderr 作为普通日志展示或保存
```

## 当前可交付边界

可以交付给前端：

```text
review_summary.json
review_sets.jsonl
previews/
thumbs/
analysis/
```

前端可开始实现：

```text
cluster list
review set 列表
primary keeper / alternate keeper
cluster 级 challenger queue
focused duel compare
reason / weakness inspector
用户 decision 写入
```

仍可后续优化但不阻塞交付：

```text
大 cluster 二次拆分
multi_embedding 权重调参
keeper 推荐策略优化
reason 文案增强
同人视图 / person view
```
