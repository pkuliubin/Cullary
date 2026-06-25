export const mockFolder = "/Users/liubin/Projects/Cullary/app/mock/cullary-demo";
export const mockSummary = {
  "schema_version": "1.1",
  "status": "success",
  "folder": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo",
  "cache_dir": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/.cullary",
  "input_manifest_path": ".cullary/manifest.jsonl",
  "review_sets_path": ".cullary/review_sets.jsonl",
  "total_photos": 12,
  "review_set_count": 1,
  "single_count": 0,
  "near_duplicate_count": 0,
  "similar_scene_count": 1,
  "recommended_keep_count": 1,
  "lower_ranked_count": 5,
  "duration_ms": 412,
  "config_hash": "demo",
  "failures": []
};
export const mockReviewSets = [
  {
    "schema_version": "1.1",
    "review_set_id": "set_demo_001",
    "set_type": "similar_scene",
    "photo_count": 12,
    "cover_display_id": "DEMO_0001_JPG",
    "recommended_keep_count": 1,
    "primary_keeper_id": "DEMO_0001_JPG",
    "recommended_keep_ids": [
      "DEMO_0001_JPG"
    ],
    "alternate_keeper_count": 1,
    "alternate_keeper_ids": [
      "DEMO_0004_JPG"
    ],
    "challenger_queue": [
      { "photo_id": "DEMO_0004_JPG", "rank": 1, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": true, "similarity_to_primary": 0.946, "score_delta": -0.105, "reason_zh": "备选保留，可重点对比" },
      { "photo_id": "DEMO_0002_JPG", "rank": 2, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.982, "score_delta": -0.035, "reason_zh": "清晰度接近，可用于替换对比" },
      { "photo_id": "DEMO_0003_JPG", "rank": 3, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.964, "score_delta": -0.07, "reason_zh": "构图不同，可用于替换对比" },
      { "photo_id": "DEMO_0005_JPG", "rank": 4, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.92, "score_delta": -0.14, "reason_zh": "清晰度接近，可用于替换对比" },
      { "photo_id": "DEMO_0006_JPG", "rank": 5, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.9, "score_delta": -0.175, "reason_zh": "清晰度接近，可用于替换对比" },
      { "photo_id": "DEMO_0007_JPG", "rank": 6, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.88, "score_delta": -0.2, "reason_zh": "构图接近，可作为低优先级对比" },
      { "photo_id": "DEMO_0008_JPG", "rank": 7, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.86, "score_delta": -0.22, "reason_zh": "构图接近，可作为低优先级对比" },
      { "photo_id": "DEMO_0009_JPG", "rank": 8, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.84, "score_delta": -0.24, "reason_zh": "构图接近，可作为低优先级对比" },
      { "photo_id": "DEMO_0010_JPG", "rank": 9, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.82, "score_delta": -0.26, "reason_zh": "构图接近，可作为低优先级对比" },
      { "photo_id": "DEMO_0011_JPG", "rank": 10, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.8, "score_delta": -0.28, "reason_zh": "构图接近，可作为低优先级对比" },
      { "photo_id": "DEMO_0012_JPG", "rank": 11, "compare_to": "DEMO_0001_JPG", "is_alternate_keeper": false, "similarity_to_primary": 0.78, "score_delta": -0.3, "reason_zh": "构图接近，可作为低优先级对比" }
    ],
    "time_range": {
      "start": "2026:06:24 10:01:00",
      "end": "2026:06:24 10:12:00",
      "duration_seconds": 660
    },
    "signals": {
      "time_span_seconds": 660,
      "embedding_similarity_min": 0.86,
      "embedding_similarity_mean": 0.92,
      "embedding_similarity_max": 0.98
    },
    "set_score": {
      "best_overall": 0.92,
      "score_spread": 0.21
    },
    "keeper_slots": [
      {
        "slot_id": "slot_1",
        "keeper_photo_id": "DEMO_0001_JPG",
        "rank": 1,
        "confidence": 0.88,
        "reason_summary_zh": [
          "人脸更清晰",
          "曝光稳定",
          "组内质量排名靠前"
        ],
        "weakness_summary_zh": [],
        "diversity_reason_zh": "最稳妥的主保留图",
        "challenger_queue": [
          {
            "photo_id": "DEMO_0002_JPG",
            "rank": 1,
            "similarity_to_keeper": 0.96,
            "score_delta": -0.035,
            "reason_zh": "清晰度接近，可用于替换对比"
          },
          {
            "photo_id": "DEMO_0003_JPG",
            "rank": 2,
            "similarity_to_keeper": 0.94,
            "score_delta": -0.07,
            "reason_zh": "清晰度接近，可用于替换对比"
          },
          {
            "photo_id": "DEMO_0005_JPG",
            "rank": 3,
            "similarity_to_keeper": 0.92,
            "score_delta": -0.14,
            "reason_zh": "清晰度接近，可用于替换对比"
          },
          {
            "photo_id": "DEMO_0006_JPG",
            "rank": 4,
            "similarity_to_keeper": 0.9,
            "score_delta": -0.175,
            "reason_zh": "清晰度接近，可用于替换对比"
          }
        ]
      },
      {
        "slot_id": "slot_2",
        "keeper_photo_id": "DEMO_0004_JPG",
        "rank": 2,
        "confidence": 0.78,
        "reason_summary_zh": [
          "构图和第一张不同",
          "保留更多场景变化"
        ],
        "weakness_summary_zh": [
          "清晰度略低于第一张"
        ],
        "diversity_reason_zh": "不同构图/表情，避免推荐过于相似",
        "challenger_queue": [
          {
            "photo_id": "DEMO_0007_JPG",
            "rank": 1,
            "similarity_to_keeper": 0.94,
            "score_delta": -0.105,
            "reason_zh": "构图接近，但质量略弱"
          },
          {
            "photo_id": "DEMO_0008_JPG",
            "rank": 2,
            "similarity_to_keeper": 0.915,
            "score_delta": -0.14,
            "reason_zh": "构图接近，但质量略弱"
          },
          {
            "photo_id": "DEMO_0009_JPG",
            "rank": 3,
            "similarity_to_keeper": 0.89,
            "score_delta": -0.175,
            "reason_zh": "构图接近，但质量略弱"
          }
        ]
      }
    ],
    "photos": [
      {
        "display_id": "DEMO_0001_JPG",
        "source_id": "source_0001",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0001_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0001_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0001_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0001_JPG/analysis.json",
        "capture_time": "2026:06:24 10:01:00",
        "rank": 1,
        "recommendation": "keep_candidate",
        "ui_initial_state": "recommended_keep",
        "similarity_to_cover": 1.0,
        "score": {
          "overall": 0.92,
          "technical_quality": 0.88,
          "face_quality": 0.9,
          "iqa": 0.8400000000000001,
          "composition": 0.87
        },
        "badges": [
          "sharp"
        ],
        "warnings": [],
        "reason_summary_zh": [
          "人脸更清晰",
          "曝光稳定",
          "组内质量排名靠前"
        ],
        "weakness_summary_zh": []
      },
      {
        "display_id": "DEMO_0002_JPG",
        "source_id": "source_0002",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0002_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0002_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0002_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0002_JPG/analysis.json",
        "capture_time": "2026:06:24 10:02:00",
        "rank": 2,
        "recommendation": "alternate",
        "ui_initial_state": "user_undecided",
        "similarity_to_cover": 0.982,
        "score": {
          "overall": 0.885,
          "technical_quality": 0.845,
          "face_quality": 0.865,
          "iqa": 0.805,
          "composition": 0.835
        },
        "badges": [
          "sharp"
        ],
        "warnings": [],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0003_JPG",
        "source_id": "source_0003",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0003_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0003_JPG.svg",
        "thumb_width": 240,
        "thumb_height": 360,
        "preview_path": ".cullary/previews/DEMO_0003_JPG.svg",
        "preview_width": 1067,
        "preview_height": 1600,
        "analysis_path": ".cullary/analysis/DEMO_0003_JPG/analysis.json",
        "capture_time": "2026:06:24 10:03:00",
        "rank": 3,
        "recommendation": "alternate",
        "ui_initial_state": "user_undecided",
        "similarity_to_cover": 0.964,
        "score": {
          "overall": 0.85,
          "technical_quality": 0.8099999999999999,
          "face_quality": 0.83,
          "iqa": 0.77,
          "composition": 0.7999999999999999
        },
        "badges": [],
        "warnings": [],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0004_JPG",
        "source_id": "source_0004",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0004_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0004_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0004_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0004_JPG/analysis.json",
        "capture_time": "2026:06:24 10:04:00",
        "rank": 4,
        "recommendation": "alternate_keeper",
        "ui_initial_state": "recommended_alternate",
        "similarity_to_cover": 0.946,
        "score": {
          "overall": 0.815,
          "technical_quality": 0.7749999999999999,
          "face_quality": 0.7949999999999999,
          "iqa": 0.735,
          "composition": 0.7649999999999999
        },
        "badges": [
          "sharp"
        ],
        "warnings": [],
        "reason_summary_zh": [
          "人脸更清晰",
          "曝光稳定",
          "组内质量排名靠前"
        ],
        "weakness_summary_zh": []
      },
      {
        "display_id": "DEMO_0005_JPG",
        "source_id": "source_0005",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0005_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0005_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0005_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0005_JPG/analysis.json",
        "capture_time": "2026:06:24 10:05:00",
        "rank": 5,
        "recommendation": "alternate",
        "ui_initial_state": "user_undecided",
        "similarity_to_cover": 0.928,
        "score": {
          "overall": 0.78,
          "technical_quality": 0.74,
          "face_quality": 0.76,
          "iqa": 0.7000000000000001,
          "composition": 0.73
        },
        "badges": [
          "sharp"
        ],
        "warnings": [],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0006_JPG",
        "source_id": "source_0006",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0006_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0006_JPG.svg",
        "thumb_width": 240,
        "thumb_height": 360,
        "preview_path": ".cullary/previews/DEMO_0006_JPG.svg",
        "preview_width": 1067,
        "preview_height": 1600,
        "analysis_path": ".cullary/analysis/DEMO_0006_JPG/analysis.json",
        "capture_time": "2026:06:24 10:06:00",
        "rank": 6,
        "recommendation": "alternate",
        "ui_initial_state": "user_undecided",
        "similarity_to_cover": 0.91,
        "score": {
          "overall": 0.745,
          "technical_quality": 0.705,
          "face_quality": 0.725,
          "iqa": 0.665,
          "composition": 0.695
        },
        "badges": [],
        "warnings": [],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0007_JPG",
        "source_id": "source_0007",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0007_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0007_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0007_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0007_JPG/analysis.json",
        "capture_time": "2026:06:24 10:07:00",
        "rank": 7,
        "recommendation": "alternate",
        "ui_initial_state": "user_undecided",
        "similarity_to_cover": 0.892,
        "score": {
          "overall": 0.71,
          "technical_quality": 0.6699999999999999,
          "face_quality": 0.69,
          "iqa": 0.63,
          "composition": 0.6599999999999999
        },
        "badges": [],
        "warnings": [],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0008_JPG",
        "source_id": "source_0008",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0008_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0008_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0008_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0008_JPG/analysis.json",
        "capture_time": "2026:06:24 10:08:00",
        "rank": 8,
        "recommendation": "lower_ranked",
        "ui_initial_state": "not_prioritized",
        "similarity_to_cover": 0.874,
        "score": {
          "overall": 0.675,
          "technical_quality": 0.635,
          "face_quality": 0.655,
          "iqa": 0.5950000000000001,
          "composition": 0.625
        },
        "badges": [],
        "warnings": [
          "low_confidence"
        ],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0009_JPG",
        "source_id": "source_0009",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0009_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0009_JPG.svg",
        "thumb_width": 240,
        "thumb_height": 360,
        "preview_path": ".cullary/previews/DEMO_0009_JPG.svg",
        "preview_width": 1067,
        "preview_height": 1600,
        "analysis_path": ".cullary/analysis/DEMO_0009_JPG/analysis.json",
        "capture_time": "2026:06:24 10:09:00",
        "rank": 9,
        "recommendation": "lower_ranked",
        "ui_initial_state": "not_prioritized",
        "similarity_to_cover": 0.856,
        "score": {
          "overall": 0.64,
          "technical_quality": 0.6,
          "face_quality": 0.62,
          "iqa": 0.56,
          "composition": 0.59
        },
        "badges": [],
        "warnings": [
          "low_confidence"
        ],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0010_JPG",
        "source_id": "source_0010",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0010_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0010_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0010_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0010_JPG/analysis.json",
        "capture_time": "2026:06:24 10:10:00",
        "rank": 10,
        "recommendation": "lower_ranked",
        "ui_initial_state": "not_prioritized",
        "similarity_to_cover": 0.838,
        "score": {
          "overall": 0.605,
          "technical_quality": 0.565,
          "face_quality": 0.585,
          "iqa": 0.525,
          "composition": 0.5549999999999999
        },
        "badges": [],
        "warnings": [
          "low_confidence"
        ],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0011_JPG",
        "source_id": "source_0011",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0011_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0011_JPG.svg",
        "thumb_width": 360,
        "thumb_height": 240,
        "preview_path": ".cullary/previews/DEMO_0011_JPG.svg",
        "preview_width": 1600,
        "preview_height": 1067,
        "analysis_path": ".cullary/analysis/DEMO_0011_JPG/analysis.json",
        "capture_time": "2026:06:24 10:11:00",
        "rank": 11,
        "recommendation": "lower_ranked",
        "ui_initial_state": "not_prioritized",
        "similarity_to_cover": 0.82,
        "score": {
          "overall": 0.57,
          "technical_quality": 0.5299999999999999,
          "face_quality": 0.5499999999999999,
          "iqa": 0.48999999999999994,
          "composition": 0.5199999999999999
        },
        "badges": [],
        "warnings": [
          "low_confidence"
        ],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      },
      {
        "display_id": "DEMO_0012_JPG",
        "source_id": "source_0012",
        "source_path": "/Users/liubin/Projects/Cullary/app/mock/cullary-demo/originals/DEMO_0012_JPG.jpg",
        "thumb_path": ".cullary/thumbs/DEMO_0012_JPG.svg",
        "thumb_width": 240,
        "thumb_height": 360,
        "preview_path": ".cullary/previews/DEMO_0012_JPG.svg",
        "preview_width": 1067,
        "preview_height": 1600,
        "analysis_path": ".cullary/analysis/DEMO_0012_JPG/analysis.json",
        "capture_time": "2026:06:24 10:12:00",
        "rank": 12,
        "recommendation": "lower_ranked",
        "ui_initial_state": "not_prioritized",
        "similarity_to_cover": 0.802,
        "score": {
          "overall": 0.535,
          "technical_quality": 0.49500000000000005,
          "face_quality": 0.515,
          "iqa": 0.455,
          "composition": 0.48500000000000004
        },
        "badges": [],
        "warnings": [
          "low_confidence"
        ],
        "reason_summary_zh": [
          "清晰度接近",
          "可作为替代候选"
        ],
        "weakness_summary_zh": [
          "表情或构图略弱"
        ]
      }
    ],
    "reason_summary_zh": [
      "同一时间段内视觉相似",
      "建议优先保留质量排名靠前且构图有差异的 2 张"
    ]
  }
];
