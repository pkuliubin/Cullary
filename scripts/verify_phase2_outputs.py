#!/usr/bin/env python3
"""Verify Cullary Phase 2 review outputs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

REQUIRED_PHOTO_FIELDS = [
    "display_id", "source_id", "source_path", "thumb_path", "thumb_width", "thumb_height",
    "preview_path", "preview_width", "preview_height", "analysis_path",
    "rank", "recommendation", "ui_initial_state", "score",
    "reason_summary_zh", "weakness_summary_zh",
]
REQUIRED_SET_FIELDS = [
    "schema_version", "review_set_id", "set_type", "photo_count", "cover_display_id",
    "primary_keeper_id", "recommended_keep_ids", "alternate_keeper_ids",
    "alternate_keeper_count", "challenger_queue", "keeper_slots", "photos", "reason_summary_zh",
]
RECOMMENDATION_TO_UI = {
    "keep_candidate": "recommended_keep",
    "alternate_keeper": "recommended_alternate",
    "alternate": "user_undecided",
    "lower_ranked": "not_prioritized",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve(folder: Path, path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else folder / p


def finite_01(value: Any, label: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise AssertionError(f"{label} must be finite 0..1, got {value!r}")


def verify(folder: Path) -> dict[str, Any]:
    cache = folder / ".cullary"
    summary_path = cache / "review_summary.json"
    sets_path = cache / "review_sets.jsonl"
    manifest_path = cache / "manifest.jsonl"
    for path in [summary_path, sets_path, manifest_path]:
        if not path.exists():
            raise AssertionError(f"missing required artifact: {path}")
    summary = load_json(summary_path)
    sets = load_jsonl(sets_path)
    manifest = load_jsonl(manifest_path)
    phase1_success = {r["display_id"] for r in manifest if r.get("status", {}).get("overall") == "success"}
    seen: set[str] = set()
    keep_count = 0
    alternate_keep_count = 0
    slot_count = 0
    challenger_count = 0
    lower_ranked_count = 0
    type_counts: dict[str, int] = {}
    for item in sets:
        for field in REQUIRED_SET_FIELDS:
            if field not in item:
                raise AssertionError(f"review set missing field {field}: {item.get('review_set_id')}")
        if item["set_type"] not in {"near_duplicate", "similar_scene", "single"}:
            raise AssertionError(f"invalid set_type: {item['set_type']}")
        type_counts[item["set_type"]] = type_counts.get(item["set_type"], 0) + 1
        photos = item["photos"]
        if len(photos) != item["photo_count"]:
            raise AssertionError(f"photo_count mismatch: {item['review_set_id']}")
        if not photos:
            raise AssertionError(f"empty review set: {item['review_set_id']}")
        photo_ids = {p["display_id"] for p in photos}
        if item["cover_display_id"] not in photo_ids:
            raise AssertionError(f"cover not in photos: {item['review_set_id']}")
        primary_id = item.get("primary_keeper_id")
        if primary_id not in photo_ids:
            raise AssertionError(f"primary_keeper_id not in photos: {item['review_set_id']}")
        if item.get("recommended_keep_ids") != [primary_id]:
            raise AssertionError(f"recommended_keep_ids must contain only primary keeper: {item['review_set_id']}")
        alternate_ids = item.get("alternate_keeper_ids", [])
        if len(alternate_ids) != item.get("alternate_keeper_count"):
            raise AssertionError(f"alternate_keeper_count mismatch: {item['review_set_id']}")
        if primary_id in alternate_ids:
            raise AssertionError(f"primary keeper cannot be alternate: {item['review_set_id']}")
        if any(photo_id not in photo_ids for photo_id in alternate_ids):
            raise AssertionError(f"alternate_keeper_ids contain unknown photo: {item['review_set_id']}")
        for entry in item.get("challenger_queue", []):
            challenger_count += 1
            if entry.get("photo_id") not in photo_ids:
                raise AssertionError(f"challenger not in photos: {item['review_set_id']}")
            if entry.get("photo_id") == primary_id:
                raise AssertionError(f"primary keeper cannot be challenger: {item['review_set_id']}")
            if entry.get("compare_to") != primary_id:
                raise AssertionError(f"challenger compare_to must be primary keeper: {item['review_set_id']}")
            finite_01(entry.get("similarity_to_primary"), "similarity_to_primary")
            if entry.get("is_alternate_keeper") != (entry.get("photo_id") in alternate_ids):
                raise AssertionError(f"challenger alternate flag mismatch: {item['review_set_id']}")
        expected_challenger_ids = photo_ids - {primary_id}
        actual_challenger_ids = {entry.get("photo_id") for entry in item.get("challenger_queue", [])}
        if expected_challenger_ids != actual_challenger_ids:
            raise AssertionError(f"challenger_queue must include every non-primary photo: {item['review_set_id']}")
        for slot in item.get("keeper_slots", []):
            slot_count += 1
            for field in ["slot_id", "keeper_photo_id", "rank", "confidence", "reason_summary_zh", "weakness_summary_zh", "diversity_reason_zh", "challenger_queue"]:
                if field not in slot:
                    raise AssertionError(f"keeper slot missing field {field}: {item['review_set_id']}")
            if slot.get("keeper_photo_id") != primary_id:
                raise AssertionError(f"compat keeper slot must point to primary keeper: {item['review_set_id']}")
            finite_01(slot.get("confidence"), "keeper_slot.confidence")
        for photo in photos:
            for field in REQUIRED_PHOTO_FIELDS:
                if field not in photo:
                    raise AssertionError(f"photo missing field {field}: {photo.get('display_id')}")
            if photo["display_id"] in seen:
                raise AssertionError(f"photo appears in multiple sets: {photo['display_id']}")
            seen.add(photo["display_id"])
            if not Path(photo["source_path"]).exists():
                raise AssertionError(f"missing source_path: {photo['source_path']}")
            for path_field in ["thumb_path", "preview_path", "analysis_path"]:
                if not resolve(folder, photo[path_field]).exists():
                    raise AssertionError(f"missing {path_field}: {photo[path_field]}")
            for dim in ["thumb_width", "thumb_height", "preview_width", "preview_height"]:
                if not isinstance(photo[dim], int) or photo[dim] <= 0:
                    raise AssertionError(f"invalid dimension {dim}: {photo[dim]}")
            for score_name in ["overall", "technical_quality", "face_quality", "iqa", "composition"]:
                finite_01(photo["score"].get(score_name), f"score.{score_name}")
            if photo["recommendation"] not in RECOMMENDATION_TO_UI:
                raise AssertionError(f"invalid recommendation: {photo['recommendation']}")
            expected_ui_state = RECOMMENDATION_TO_UI[photo["recommendation"]]
            if photo["ui_initial_state"] != expected_ui_state:
                raise AssertionError(f"{photo['recommendation']} must map to {expected_ui_state}")
            if photo["recommendation"] == "keep_candidate":
                keep_count += 1
                if photo["display_id"] != primary_id:
                    raise AssertionError(f"only primary keeper can be keep_candidate: {item['review_set_id']}")
            if photo["recommendation"] == "alternate_keeper":
                alternate_keep_count += 1
                if photo["display_id"] not in alternate_ids:
                    raise AssertionError(f"alternate_keeper photo not listed in alternate_keeper_ids: {item['review_set_id']}")
            if photo["recommendation"] == "lower_ranked":
                lower_ranked_count += 1
            if not isinstance(photo["reason_summary_zh"], list) or not isinstance(photo["weakness_summary_zh"], list):
                raise AssertionError("photo reasons must be lists")
    if seen != phase1_success:
        missing = sorted(phase1_success - seen)[:10]
        extra = sorted(seen - phase1_success)[:10]
        raise AssertionError(f"review photos mismatch phase1 success. missing={missing} extra={extra}")
    if summary.get("status") != "success":
        raise AssertionError(f"summary status not success: {summary.get('status')}")
    if summary.get("total_photos") != len(seen):
        raise AssertionError("summary total_photos mismatch")
    if summary.get("review_set_count") != len(sets):
        raise AssertionError("summary review_set_count mismatch")
    if summary.get("recommended_keep_count") != keep_count:
        raise AssertionError("summary recommended_keep_count mismatch")
    if summary.get("alternate_keeper_count") != alternate_keep_count:
        raise AssertionError("summary alternate_keeper_count mismatch")
    if summary.get("keeper_slot_count") != slot_count:
        raise AssertionError("summary keeper_slot_count mismatch")
    if summary.get("challenger_count") != challenger_count:
        raise AssertionError("summary challenger_count mismatch")
    if summary.get("lower_ranked_count") != lower_ranked_count:
        raise AssertionError("summary lower_ranked_count mismatch")
    for field in ["schema_version", "folder", "cache_dir", "input_manifest_path", "review_sets_path", "single_count", "near_duplicate_count", "similar_scene_count", "lower_ranked_count", "duration_ms", "config_hash", "input_hash", "cache_hit", "failures"]:
        if field not in summary:
            raise AssertionError(f"summary missing field {field}")
    if summary.get("single_count") != type_counts.get("single", 0):
        raise AssertionError("summary single_count mismatch")
    if summary.get("near_duplicate_count") != type_counts.get("near_duplicate", 0):
        raise AssertionError("summary near_duplicate_count mismatch")
    if summary.get("similar_scene_count") != type_counts.get("similar_scene", 0):
        raise AssertionError("summary similar_scene_count mismatch")
    return {
        "status": "success",
        "folder": str(folder),
        "review_set_count": len(sets),
        "total_photos": len(seen),
        "recommended_keep_count": keep_count,
        "alternate_keeper_count": alternate_keep_count,
        "keeper_slot_count": slot_count,
        "challenger_count": challenger_count,
        "lower_ranked_count": lower_ranked_count,
        "type_counts": type_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 2 review outputs")
    parser.add_argument("folder")
    args = parser.parse_args()
    try:
        result = verify(Path(args.folder).expanduser().resolve())
    except AssertionError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
