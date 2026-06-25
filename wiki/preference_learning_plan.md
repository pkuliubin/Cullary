# Preference Learning 计划：基于用户筛选行为的 Ranking Model

## 定位

这部分不是训练图片大模型，也不是替换当前的 DINOv2 / image analyzer。

目标是基于 Cullary 已经抽取好的数据，学习用户自己的筛选偏好：

```text
photo features + cluster context + user decisions
  -> user_preference_score
  -> 更符合用户审美的组内排序
```

当前 Phase 1 / Phase 2 已经产出足够多的基础特征；后续用户在 UI 中产生的 keep / 待删除 / replace / keep-both 等行为，可以转成训练数据。

## 为什么可行

即使原图后续被移走或删除，只要 `.cullary/` 保留，我们仍然有：

```text
preview / thumb
analysis JSON
embedding vectors
foreground / background embedding
review_sets.jsonl
decisions.jsonl
preference_events.jsonl
```

所以后续可以继续基于这些缓存数据构建训练集。

关键是不要只保留用户事件，还要能关联回当时的图片特征和 cluster 上下文。

## 数据来源

### 用户行为数据

来自 UI / Rust 写入的事件文件：

```text
.cullary/decisions.jsonl
.cullary/preference_events.jsonl
```

典型行为：

```text
user_keep
user_marked_move_aside
user_undecided
replace_with_challenger
keep_both
skip_challenger
accept_cluster
```

其中最有价值的是 pairwise 行为：

```text
A vs B
用户选择 B replace A
=> B > A
```

### 图片特征数据

来自 Phase 1：

```text
.cullary/analysis/<display_id>/analysis.json
.cullary/embeddings/<display_id>.npy
.cullary/foreground_embeddings/<display_id>.npy
.cullary/background_embeddings/<display_id>.npy
```

主要包括：

```text
image_metrics
face_metrics
iqa_metrics
person_mask / foreground_area_ratio
global_embedding
foreground_embedding
background_embedding
```

### Cluster 上下文

来自 Phase 2：

```text
.cullary/review_sets.jsonl
```

可用字段：

```text
review_set_id
set_type
photo_count
primary_keeper_id
alternate_keeper_ids
challenger_queue
photos[].rank
photos[].score
photos[].recommendation
photos[].ui_initial_state
similarity_to_primary
score_delta
```

## 训练样本类型

### Pairwise 样本

最重要。

```json
{
  "sample_type": "pairwise",
  "review_set_id": "set_000012",
  "winner_id": "B0007115_3FR",
  "loser_id": "B0007114_3FR",
  "source_event": "replace_with_challenger",
  "weight": 1.0
}
```

来源规则：

```text
replace_with_challenger: challenger > old keeper
keep_current: keeper > challenger
keep_both: 两者都偏正，pairwise 信号较弱
user_keep vs user_marked_move_aside: keep > move_aside
accept_cluster: 系统推荐被接受，可作为弱标签
skip_challenger: 弱信号，不应直接当强负样本
```

### Pointwise 样本

辅助使用。

```json
{
  "sample_type": "pointwise",
  "review_set_id": "set_000012",
  "photo_id": "B0007115_3FR",
  "label": 1,
  "source_event": "user_keep",
  "weight": 0.6
}
```

pointwise 比 pairwise 更容易受 cluster 难度影响，所以第一版以 pairwise 为主。

## Feature 设计

### Wide 特征

Wide 部分使用结构化、可解释特征。

质量类：

```text
sharpness_laplacian_var
sharpness_tenengrad
brightness_mean
shadow_clip_ratio
highlight_clip_ratio
contrast_std_ratio
dynamic_range_p05_p95
saturation_mean
color_cast_strength
iqa_score
```

人像类：

```text
face_count
largest_face_area_ratio
face_sharpness
face_alignment_score
foreground_area_ratio
```

构图类：

```text
aspect_ratio
orientation
center_brightness_delta
center_sharpness_ratio
face_center_offset
```

Cluster 相对类：

```text
rank
base_quality_score
technical_quality
face_quality
composition
similarity_to_primary
score_delta_to_primary
is_alternate_keeper
set_type
photo_count
```

交叉特征可以逐步增加：

```text
has_face AND face_sharpness_high
foreground_area_ratio_medium AND composition_good
highlight_clip_low AND has_face
similarity_high AND score_delta_positive
portrait AND face_centered
```

### Deep 特征

Deep 部分使用 embedding：

```text
global_embedding
foreground_embedding
background_embedding
```

如果没有 foreground/background embedding：

```text
向量填 0
额外提供 has_foreground_embedding / has_background_embedding mask flag
```

## 推荐模型路线

### Step 1：Baseline Logistic / Linear Ranker

第一版先做这个。

```text
input = feature_diff(winner, loser)
label = 1
loss = binary logistic loss
```

优点：

```text
快
稳定
可解释
适合早期少量数据
可以输出 feature 权重
```

### Step 2：Wide & Deep Pairwise Ranker

用户明确倾向的中期方向。

推荐使用 Siamese ranking 结构：

```text
score(photo) = wide(photo) + deep(photo)
loss = -log sigmoid(score(winner) - score(loser))
```

结构：

```text
wide numeric/cross features -> Linear -> wide_score

global/foreground/background embedding + mask flags
  -> MLP
  -> deep_score

final_score = wide_score + deep_score + bias
```

示例维度：

```text
wide_features: 30-80 dims
embedding_features: 384 * 3 + mask flags
MLP: 1152 -> 256 -> 64 -> 1
```

### Step 3：LightGBM / XGBoost Ranker

可作为 tabular ranking 对照方案。

优点：

```text
非线性能力强
对结构化特征友好
训练快
```

缺点：

```text
embedding 直接输入维度较高
解释性比 linear 弱
本地依赖需要确认
```

## 数据量策略

```text
< 100 pairwise events:
  只使用 wide / logistic，不启用 deep

100 - 1000 pairwise events:
  wide + 小型 deep MLP，强正则，低 preference 权重

> 1000 pairwise events:
  完整 wide & deep，可加入 foreground/background embedding
```

早期不要让个性化模型过度影响推荐。

## 和 Phase 2 的融合方式

Phase 2 当前有基础质量分：

```text
base_quality_score
```

训练出偏好模型后，可以增加：

```text
user_preference_score
```

最终排序：

```text
final_score =
  base_quality_score * (1 - preference_weight)
  + user_preference_score * preference_weight
```

`preference_weight` 随数据量增长：

```text
preference_weight = min(0.4, pairwise_samples / 1000 * 0.4)
```

也就是说，用户筛得越多，个性化影响越大。

## 产物设计

建议新增目录：

```text
.cullary/preference/
```

产物：

```text
preference_dataset.jsonl
pairwise_samples.jsonl
pointwise_samples.jsonl
feature_schema.json
model.pt
model.pkl
model_card.json
scores.jsonl
```

`model_card.json` 示例：

```json
{
  "model_type": "wide_deep_pairwise_ranker",
  "trained_at": "2026-06-25T12:00:00+08:00",
  "pairwise_samples": 842,
  "pointwise_samples": 1260,
  "wide_feature_dim": 48,
  "embedding_dim": 1152,
  "validation_auc": 0.71,
  "preference_weight_recommendation": 0.34,
  "wide_top_weights": [
    ["face_sharpness_diff", 0.8],
    ["highlight_clip_ratio_diff", -0.5]
  ]
}
```

## CLI 设想

偏好学习不应该阻塞主 pipeline，建议做成独立模块：

```bash
PYTHONPATH=src python -m cullary.preference build-dataset /path/to/folder
PYTHONPATH=src python -m cullary.preference train /path/to/folder
PYTHONPATH=src python -m cullary.preference score /path/to/folder
```

未来也可以支持跨多个 `.cullary` 目录训练全局用户模型：

```bash
PYTHONPATH=src python -m cullary.preference train-global paths.md
```

## 风险与约束

- 用户决策事件必须稳定记录，否则训练样本不可追溯。
- 如果原图删除，仍可基于 preview / embedding / analysis 训练，但无法重新生成新 analyzer 特征。
- 早期数据少，deep 部分容易过拟合。
- `skip` 和 `accept_cluster` 是弱信号，不能简单等同于强负/强正。
- 不同拍摄场景难度不同，pointwise label 需要谨慎加权。
- 模型输出只能影响推荐排序，不应自动删除或移动照片。

## 阶段边界

短期不做：

```text
微调 DINOv2 / CLIP
训练图像生成或图像理解大模型
用偏好模型自动删除文件
跨用户共享偏好模型
```

优先做：

```text
稳定记录 decision / preference events
构建 pairwise preference dataset
训练 baseline logistic ranker
评估是否比 base_quality_score 更符合用户选择
再升级 wide & deep pairwise ranker
```
