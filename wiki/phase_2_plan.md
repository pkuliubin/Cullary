# Phase 2 计划：Review Set Generation

Phase 2 的目标不是只做算法层面的 clustering，而是产出前端可以直接渲染的 cluster-level review 数据结构。

输入是 Phase 1 生成的 `.cullary/` 分析结果；输出是按相似场景组织好的 review set，并在每个 set 内给出一个 primary keeper、若干 alternate keeper、全局 challenger queue、排序、评分和结构化解释。

Phase 2 仍然不移动、不删除、不改名源文件。所有推荐都只是候选建议，最终操作由用户在后续 UI / file operation 阶段确认。

## 阶段定位

Phase 2 = clustering + scoring + primary keeper recommendation + cluster-level UI-ready schema。

处理链路：

```text
Phase 1 单图分析结果
  -> 时间 session 切分
  -> session 内 embedding 相似度分组
  -> review set 生成
  -> 组内质量评分和排序
  -> primary keeper / alternate keeper 推荐
  -> cluster 级 challenger queue 生成
  -> 兼容 keeper_slots 生成
  -> 前端可渲染 review_sets.jsonl
```

Phase 2 结束后，前端应该可以展示：

- 一共有多少个 review set。
- 每组有哪些照片。
- 每组的 primary keeper 是哪张。
- 哪些照片是 alternate keeper。
- 全局 challenger queue 是什么顺序。
- 每张图的排序、评分、warning、badge。
- 推荐原因、弱点原因和主要扣分原因。
- 用户可以按 Keeper 池 / Challenger 池，以及 focused duel 的方式进行 review。

## 输入

来自 Phase 1：

```text
<input_folder>/.cullary/manifest.jsonl
<input_folder>/.cullary/analysis/<display_id>/analysis.json
<input_folder>/.cullary/embeddings/<display_id>.npy
```

要求：

- 只读取 Phase 1 产物，不重新跑 analyzer。
- 不依赖 SQLite。
- 不读取源图大文件，UI 展示使用 preview/thumb。
- 如果部分模型结果失败，仍应给出 review set，但评分解释中标记缺失项。

## 输出

```text
<input_folder>/.cullary/review_sets.jsonl
<input_folder>/.cullary/review_summary.json
```

可选调试输出：

```text
<input_folder>/.cullary/review_debug.json
```

## 不做的事情

- 不移动、不删除、不改名文件。
- 不做永久用户决策记录。
- 不做 face embedding / 同人聚类。
- 不把 pHash/dHash 作为主分组逻辑。
- 不做复杂数据库查询层。

## 分组策略

### 主信号

Phase 2 主分组信号：

```text
capture time + embedding similarity
```

具体策略：

1. 从 metadata 中解析拍摄时间。
2. 按时间排序照片。
3. 只在候选时间窗口内比较 embedding，避免全库两两比较。
4. 日期变化、超大时间 gap、相机设备变化作为 hard break，不跨 hard segment 连边。
5. 在 hard segment 内使用 embedding cosine similarity 建图。
6. 根据 similarity threshold 找连通分量，生成 review set。
7. 单张孤立照片也生成 `single` review set，保证不丢图。

### pHash/dHash 的定位

pHash/dHash 暂不作为主逻辑。

原因：

- 当前 embedding 已经是主要视觉相似度来源。
- 如果 pHash 能判断明显重复，embedding 通常也能覆盖。
- 过早混入 hash 规则会让分组解释和阈值调试更复杂。

保留用途：

- debug signal。
- 后续极端近重复 fallback。
- 后续性能优化或异常 case 辅助。

## Review Set 类型

建议第一版使用这些类型：

```text
near_duplicate   # 高相似度，通常是连拍/重复构图
similar_scene    # 同一场景，角度或构图略有变化
single           # 无相似同组照片
```

判定方式先保持简单：

- `near_duplicate`：组内 embedding similarity 很高，时间跨度较短。
- `similar_scene`：组内 similarity 达到阈值，但差异更大或时间跨度更长。
- `single`：只有 1 张。

## 默认配置

建议新增配置：

```json
{
  "review": {
    "candidate_time_window_seconds": 1800,
    "candidate_neighbor_limit": 40,
    "hard_time_gap_seconds": 3600,
    "embedding_similarity_threshold": 0.86,
    "near_duplicate_similarity_threshold": 0.93,
    "challenger_queue_size": 5,
    "keeper_policy": {
      "max_keep_count": 3,
      "small_set_keep_count": 1,
      "medium_set_keep_count": 2,
      "large_set_keep_count": 3,
      "medium_set_min_size": 4,
      "large_set_min_size": 9
    }
  }
}
```

这些阈值第一版可以通过样本调试，后续保留在配置里迭代。

## 评分策略

Phase 2 开始把 Phase 1 的 raw metrics 转成组内可比较的分数。

注意：不同指标量纲不同，不能直接相加。需要先做归一化，再按大类加权。

### 评分大类

```text
technical_quality
  - sharpness
  - exposure
  - contrast
  - color

face_quality
  - face_sharpness
  - face_size
  - alignment
  - detection_confidence

iqa
  - piqe

composition
  - center_sharpness
  - center_brightness
  - orientation / aspect fit
```

### 归一化原则

第一版优先使用 review set 内归一化：

```text
raw metrics within review set
  -> robust normalization
  -> category score
  -> weighted overall score
```

建议：

- sharpness：组内越高越好。
- exposure：死黑/死白越少越好，brightness 不过暗不过亮。
- contrast：过低扣分，极端过高也可轻微扣分。
- color：过饱和、明显偏色扣分。
- face：有人脸时，人脸清晰度、面积、alignment、score 越高越好。
- PIQE：lower is better，需要反向归一化。
- composition：先做轻量辅助，不要过度影响第一版推荐。

### 缺失数据处理

- 如果某类数据缺失，不让整张图评分失败。
- 缺失类目记录在 `score_missing`。
- overall score 使用可用类目的权重重新归一。
- reason 中明确说明哪些数据缺失。

## Keeper 推荐策略

Phase 2 做 keeper candidate 推荐，但不做文件操作。

第一版规则：

```text
photo_count <= 3: 推荐 1 张
4 <= photo_count <= 8: 推荐 1-2 张
photo_count >= 9: 推荐 2-3 张
```

候选选择：

- 按 `overall_score` 排序。
- 如果有明显多人脸/人像场景，可保留 face score 更好的图。
- 如果 top 分数差距很小，可以推荐多张。
- 每个 review set 至少推荐 1 张。

输出中区分：

```text
recommendation: keep_candidate | alternate | lower_ranked
```

给 UI 的初始状态映射：

```text
keep_candidate -> recommended_keep
alternate      -> challenger
lower_ranked   -> not_prioritized
```

用户操作后的状态不由 Phase 2 产生，后续 UI / decision 阶段再写入：

```text
user_keep
user_marked_move_aside
user_undecided
```

不要输出最终 delete/reject 决策，避免 UI 上给用户造成已决定删除的感觉。

## 输出 Schema

### review_sets.jsonl

一行一个 review set。

示例：

```json
{
  "schema_version": "1.1",
  "review_set_id": "set_000001",
  "set_type": "similar_scene",
  "photo_count": 6,
  "cover_display_id": "B0007796_HEIC",
  "primary_keeper_id": "B0007796_HEIC",
  "recommended_keep_count": 1,
  "recommended_keep_ids": ["B0007796_HEIC"],
  "alternate_keeper_count": 1,
  "alternate_keeper_ids": ["B0007798_HEIC"],
  "challenger_queue": [
    {
      "photo_id": "B0007798_HEIC",
      "rank": 1,
      "compare_to": "B0007796_HEIC",
      "is_alternate_keeper": true,
      "similarity_to_primary": 0.94,
      "score_delta": -0.03,
      "reason_zh": "综合评分接近，值得对比"
    },
    {
      "photo_id": "B0007797_HEIC",
      "rank": 2,
      "compare_to": "B0007796_HEIC",
      "is_alternate_keeper": false,
      "similarity_to_primary": 0.96,
      "score_delta": -0.04,
      "reason_zh": "清晰度接近，但表情略弱"
    }
  ],
  "time_range": {
    "start": "2025:10:02 19:16:49",
    "end": "2025:10:02 19:17:03",
    "duration_seconds": 14
  },
  "signals": {
    "time_span_seconds": 14,
    "embedding_similarity_min": 0.89,
    "embedding_similarity_mean": 0.94,
    "embedding_similarity_max": 0.98
  },
  "set_score": {
    "best_overall": 0.82,
    "score_spread": 0.18
  },
  "keeper_slots": [
    {
      "slot_id": "slot_1",
      "keeper_photo_id": "B0007796_HEIC",
      "rank": 1,
      "confidence": 0.86,
      "reason_summary_zh": [
        "人脸更清晰",
        "曝光稳定",
        "组内质量排名靠前"
      ],
      "weakness_summary_zh": [
        "与另一张推荐图较相似"
      ],
      "diversity_reason_zh": "与第二张推荐图构图不同",
      "challenger_queue": [
        {
          "photo_id": "B0007797_HEIC",
          "rank": 1,
          "similarity_to_keeper": 0.96,
          "score_delta": -0.04,
          "reason_zh": "清晰度接近，但表情略弱"
        }
      ]
    }
  ],
  "photos": [
    {
      "display_id": "B0007796_HEIC",
      "source_id": "...",
      "source_path": "/Users/liubin/Desktop/TestImage/B0007796.HEIC",
      "thumb_path": ".cullary/thumbs/B0007796_HEIC.jpg",
      "thumb_width": 360,
      "thumb_height": 270,
      "preview_path": ".cullary/previews/B0007796_HEIC.jpg",
      "preview_width": 1600,
      "preview_height": 1200,
      "analysis_path": ".cullary/analysis/B0007796_HEIC/analysis.json",
      "capture_time": "2025:10:02 19:16:49",
      "rank": 1,
      "recommendation": "keep_candidate",
      "ui_initial_state": "recommended_keep",
      "similarity_to_cover": 1.0,
      "score": {
        "overall": 0.82,
        "technical_quality": 0.78,
        "face_quality": 0.9,
        "iqa": 0.7,
        "composition": 0.75
      },
      "badges": ["sharp", "face_good"],
      "warnings": [],
      "reason_summary_zh": [
        "人脸清晰",
        "曝光稳定",
        "组内质量排名靠前"
      ],
      "weakness_summary_zh": [
        "与另一张候选图相似度较高"
      ]
    }
  ],
  "reason_summary_zh": [
    "同一时间段内视觉相似",
    "建议优先保留质量排名靠前的 2 张"
  ]
}
```

字段要求：

- `primary_keeper_id` 是系统默认主推荐。
- `recommended_keep_ids` 第一版只包含 `primary_keeper_id`，用于前端初始化 Keeper 池。
- `alternate_keeper_ids` 是质量较高的备选保留候选，但不默认进入 Keeper 池。
- 顶层 `challenger_queue` 是 cluster 级 focused duel compare 队列，包含所有非 primary 照片。
- `keeper_slots` 仅作为短期兼容字段保留，不再作为前端主合约。
- `photos[]` 必须包含 thumb/preview 尺寸，避免前端布局抖动。
- `photos[]` 必须包含 `source_path`，供 Rust-owned final staging 生成 dry-run / move plan。UI 不直接使用它渲染图片。
- `reason_summary_zh` / `weakness_summary_zh` 使用数组，方便 inspector 稳定排版。
- `ui_initial_state` 是 Phase 2 recommendation 到 UI 初始状态的显式映射。

### review_summary.json

示例：

```json
{
  "schema_version": "1.1",
  "status": "success",
  "folder": "/Users/liubin/Desktop/TestImage",
  "cache_dir": "/Users/liubin/Desktop/TestImage/.cullary",
  "input_manifest_path": ".cullary/manifest.jsonl",
  "review_sets_path": ".cullary/review_sets.jsonl",
  "total_photos": 113,
  "review_set_count": 28,
  "single_count": 9,
  "near_duplicate_count": 11,
  "similar_scene_count": 8,
  "recommended_keep_count": 38,
  "alternate_keeper_count": 9,
  "keeper_slot_count": 38,
  "challenger_count": 75,
  "lower_ranked_count": 23,
  "duration_ms": 1234,
  "config_hash": "...",
  "failures": []
}
```

## UI 消费方式

Phase 2 输出应直接支撑前端：

- 任务概览读取 `review_summary.json`。
- Review 列表读取 `review_sets.jsonl`。
- 卡片封面使用 `cover_display_id` 对应的 `thumb_path`。
- 组内缩略图使用 `photos[].thumb_path`。
- 对比视图使用 `photos[].preview_path`。
- 详情面板按需读取 `photos[].analysis_path`。
- UI 默认把 `ui_initial_state = recommended_keep` 的照片放入 Keeper 池。
- `ui_initial_state = recommended_alternate` 的照片作为备选，不默认进入 Keeper 池。
- Deck / Compare 优先读取 `primary_keeper_id`、`alternate_keeper_ids`、顶层 `challenger_queue`。
- Focused duel compare 从全局 Challenger 池取下一张，不从 per-slot queue 推断。
- Inspector 直接展示 `reason_summary_zh[]` 和 `weakness_summary_zh[]`。

前端不应该自己重新计算推荐分数，也不应该自己推断 keeper/challenger 关系；前端只展示 Phase 2 的 review model。

## 恢复与跳过

Phase 2 也需要支持重复运行跳过。

输入变化判断：

- `manifest.jsonl` 内容 hash。
- 每张照片 `analysis_path` 中关键 analyzer status/version/config_hash。
- embedding vector 文件存在与 mtime。
- Phase 2 自己的 review config hash。

如果输入和配置未变化：

- 直接复用 `review_sets.jsonl` 和 `review_summary.json`。

如果部分 Phase 1 结果变化：

- 第一版可以重算全部 review sets。
- 后续再做 session 级增量。

## 实施步骤

### Step 1：Review 输入加载器

- 读取 manifest。
- 读取 analysis JSON。
- 读取 embedding `.npy`。
- 构造内存中的 photo view model。
- 校验所有 Phase 1 成功照片都可进入 Phase 2。

### Step 2：时间 session 切分

- 解析 `date_time_original` / `create_date`。
- 时间缺失时 fallback 到文件 mtime。
- 按时间排序后构造 hard segment。
- 在每个 hard segment 内用 `candidate_time_window_seconds` 和 `candidate_neighbor_limit` 限制候选比较。
- 输出 hard segment、候选比较数量、连边数量等 debug 信息。

### Step 3：Embedding 相似度分组

- 每张图只与 hard segment 内、候选时间窗口内、邻近数量上限内的照片计算 cosine similarity。
- 根据 threshold 建图。
- 连通分量生成初始 review set。
- 单张图生成 single set。

### Step 4：组内评分

- 从 Phase 1 metrics 计算 category score。
- 做组内归一化。
- 生成 overall score、badges、warnings、reason。

### Step 5：Keeper candidate 推荐

- 按 keeper policy 计算候选保留数量。
- 排名第一的 candidate 输出为 `primary_keeper_id` / `keep_candidate`。
- 其余高质量 candidate 输出为 `alternate_keeper_ids` / `alternate_keeper`。
- 其他重点对比候选输出为 `alternate`，更低优先级输出为 `lower_ranked`。

### Step 6：Cluster-level review 结构生成

- 生成顶层 `primary_keeper_id`。
- 生成顶层 `alternate_keeper_ids`。
- 生成顶层 `challenger_queue`，包含所有非 primary 照片。
- 生成兼容 `keeper_slots`，但只作为旧 UI 过渡字段。
- 补齐 thumb/preview 尺寸。
- 生成结构化中文推荐理由和弱点理由。
- 写入 `ui_initial_state`，避免前端重复推断。

### Step 7：输出 review model

- 写 `review_sets.jsonl`。
- 写 `review_summary.json`。
- 提供验证脚本。

## 验证计划

使用当前测试目录：

```text
/Users/liubin/Desktop/TestImage
```

验证项：

- 所有 113 张 Phase 1 成功照片都进入 review set。
- `sum(photo_count) == total_photos`。
- 每个 review set 至少有 1 张照片。
- 每个 review set 至少有 1 个 `primary_keeper_id`。
- `recommended_keep_ids` 只包含 primary keeper。
- `alternate_keeper_ids` 只能包含非 primary 照片。
- 多图 review set 的顶层 `challenger_queue` 应包含所有非 primary 照片。
- 每张照片只属于一个 review set。
- 所有 `thumb_path`、`preview_path`、`analysis_path` 存在。
- 所有 `thumb_width/thumb_height/preview_width/preview_height` 存在且为正数。
- embedding 相似度为有限数值。
- score 为 0-1 有限数值。
- `reason_summary_zh`、`weakness_summary_zh`、badges、warnings 可被 UI 直接展示。
- `review_summary.json` 与 `review_sets.jsonl` 统计一致。
- 重复运行 cache hit。

## 完成标准

Phase 2 完成时应满足：

- 一个正式 CLI 可以从 `.cullary/` 生成 `review_sets.jsonl` 和 `review_summary.json`。
- 输出结果足够前端直接渲染 review 页面。
- 所有照片都被分配到 review set。
- 每组照片都有排序、评分、primary keeper / alternate keeper 和解释。
- 每组有明确 cluster 级 challenger queue，前端不需要再推断推荐关系。
- 每张照片有图片尺寸和 UI 初始状态。
- 不发生任何源文件移动、删除、改名。
- 支持重复运行跳过未变化结果。
