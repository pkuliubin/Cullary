#!/usr/bin/env python3
"""Export preview images grouped by review set for manual cluster QA."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def resolve(folder: Path, path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else folder / p


def export(folder: Path, *, clean: bool = False) -> dict[str, Any]:
    cache = folder / ".cullary"
    review_sets_path = cache / "review_sets.jsonl"
    out_root = cache / "cluster_review"
    if not review_sets_path.exists():
        raise FileNotFoundError(f"missing review sets: {review_sets_path}")
    if clean and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    sets = load_jsonl(review_sets_path)
    exported = 0
    missing: list[dict[str, str]] = []
    index: list[dict[str, Any]] = []
    for item in sets:
        set_id = item["review_set_id"]
        dirname = f"{set_id}__{item['set_type']}__{item['photo_count']:03d}_photos"
        set_dir = out_root / dirname
        set_dir.mkdir(parents=True, exist_ok=True)
        set_index = {
            "review_set_id": set_id,
            "set_type": item["set_type"],
            "photo_count": item["photo_count"],
            "recommended_keep_ids": item.get("recommended_keep_ids", []),
            "photos": [],
        }
        rank_by_id = {p["display_id"]: p.get("rank", 0) for p in item.get("photos", [])}
        keep_ids = set(item.get("recommended_keep_ids", []))
        for photo in sorted(item.get("photos", []), key=lambda p: p.get("rank", 999999)):
            src = resolve(folder, photo.get("preview_path", ""))
            display_id = photo["display_id"]
            rank = int(rank_by_id.get(display_id) or photo.get("rank") or 0)
            keep_prefix = "KEEP" if display_id in keep_ids else "ALT"
            suffix = src.suffix or ".jpg"
            dst_name = f"{rank:02d}__{keep_prefix}__{safe_name(display_id)}{suffix}"
            dst = set_dir / dst_name
            if not src.exists():
                missing.append({"review_set_id": set_id, "display_id": display_id, "preview_path": str(src)})
                continue
            shutil.copy2(src, dst)
            exported += 1
            set_index["photos"].append({
                "rank": rank,
                "display_id": display_id,
                "recommendation": photo.get("recommendation"),
                "ui_initial_state": photo.get("ui_initial_state"),
                "score": photo.get("score", {}).get("overall"),
                "file": dst_name,
            })
        (set_dir / "set_manifest.json").write_text(json.dumps(set_index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        index.append({
            "directory": dirname,
            "review_set_id": set_id,
            "set_type": item["set_type"],
            "photo_count": item["photo_count"],
            "recommended_keep_ids": item.get("recommended_keep_ids", []),
        })
    summary = {
        "status": "success",
        "output_dir": str(out_root),
        "review_set_count": len(sets),
        "exported_preview_count": exported,
        "missing_preview_count": len(missing),
        "missing": missing,
        "sets": index,
    }
    (out_root / "index.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export grouped preview images for manual cluster review")
    parser.add_argument("folder", help="Photo folder containing .cullary/review_sets.jsonl")
    parser.add_argument("--clean", action="store_true", help="Remove existing .cullary/cluster_review before exporting")
    args = parser.parse_args()
    try:
        result = export(Path(args.folder).expanduser().resolve(), clean=args.clean)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({k: v for k, v in result.items() if k != "sets"}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
