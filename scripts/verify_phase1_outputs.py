#!/usr/bin/env python3
"""Verify Cullary Phase 1 preprocessing outputs for a photo folder."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

REQUIRED_ANALYZERS = ["metadata", "preview", "thumb", "hash", "image_metrics", "embedding", "face", "iqa"]
REQUIRED_ANALYSIS_KEYS = [
    "metadata",
    "hash",
    "image_metrics",
    "embedding",
    "face_metrics",
    "iqa_metrics",
    "score_features",
    "analyzer_status",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> list[dict[str, Any]]:
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except Exception as exc:
            raise AssertionError(f"manifest line {lineno} is not valid JSON: {exc}") from exc
    return records


def resolve(folder: Path, maybe_relative: str) -> Path:
    path = Path(maybe_relative)
    return path if path.is_absolute() else folder / path


def finite_number(value: Any, label: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AssertionError(f"{label} must be a finite number, got {value!r}")


def verify_embedding(path: Path, expected_dim: int) -> None:
    try:
        import numpy as np
    except Exception as exc:
        raise AssertionError(f"numpy is required to verify embedding npy files: {exc}") from exc
    arr = np.load(path)
    if arr.shape != (expected_dim,):
        raise AssertionError(f"embedding shape mismatch for {path}: {arr.shape} != ({expected_dim},)")
    if not np.isfinite(arr).all():
        raise AssertionError(f"embedding contains non-finite values: {path}")


def verify_folder(folder: Path) -> dict[str, Any]:
    cache = folder / ".cullary"
    manifest_path = cache / "manifest.jsonl"
    summary_path = cache / "run_summary.json"
    task_state_path = cache / "task_state.json"
    config_path = cache / "config.snapshot.json"

    for path in [cache, manifest_path, summary_path, task_state_path, config_path]:
        if not path.exists():
            raise AssertionError(f"missing required path: {path}")

    manifest = load_manifest(manifest_path)
    if not manifest:
        raise AssertionError("manifest has no records")

    summary = load_json(summary_path)
    task_state = load_json(task_state_path)
    if summary.get("status") not in {"success", "partial_success"}:
        raise AssertionError(f"unexpected summary status: {summary.get('status')}")
    if task_state.get("status") not in {"success", "partial_success", "running"}:
        raise AssertionError(f"unexpected task status: {task_state.get('status')}")

    counts = {
        "manifest_records": len(manifest),
        "analysis_json": 0,
        "previews": 0,
        "thumbs": 0,
        "embeddings": 0,
        "status_success_records": 0,
        "face_records": 0,
        "iqa_records": 0,
    }

    for record in manifest:
        source_id = record.get("source_id")
        display_id = record.get("display_id")
        if not source_id or not display_id:
            raise AssertionError(f"record missing source_id/display_id: {record}")

        analysis_path = resolve(folder, record["analysis_path"])
        if not analysis_path.exists():
            raise AssertionError(f"missing analysis json: {analysis_path}")
        counts["analysis_json"] += 1
        analysis = load_json(analysis_path)
        for key in REQUIRED_ANALYSIS_KEYS:
            if key not in analysis:
                raise AssertionError(f"{analysis_path} missing key: {key}")

        assets = record.get("assets", {})
        preview_path = resolve(folder, assets.get("preview_path", ""))
        thumb_path = resolve(folder, assets.get("thumb_path", ""))
        if not preview_path.exists():
            raise AssertionError(f"missing preview: {preview_path}")
        if not thumb_path.exists():
            raise AssertionError(f"missing thumb: {thumb_path}")
        counts["previews"] += 1
        counts["thumbs"] += 1

        statuses = analysis.get("analyzer_status", {})
        for analyzer in REQUIRED_ANALYZERS:
            status = statuses.get(analyzer, {})
            if status.get("status") != "success":
                raise AssertionError(f"{analysis_path} analyzer {analyzer} is not success: {status}")
            if not status.get("version") or not status.get("config_hash"):
                raise AssertionError(f"{analysis_path} analyzer {analyzer} missing version/config_hash")

        embedding = analysis.get("embedding", {})
        vector_path = resolve(folder, embedding.get("vector_path", ""))
        if not vector_path.exists():
            raise AssertionError(f"missing embedding vector: {vector_path}")
        verify_embedding(vector_path, int(embedding.get("dim", 384)))
        counts["embeddings"] += 1

        metrics = analysis.get("image_metrics", {})
        finite_number(metrics.get("exposure", {}).get("brightness_mean"), "brightness_mean")
        finite_number(metrics.get("sharpness", {}).get("laplacian_var"), "laplacian_var")
        finite_number(metrics.get("contrast", {}).get("contrast_std_ratio"), "contrast_std_ratio")

        face = analysis.get("face_metrics", {})
        if not isinstance(face.get("face_count"), int):
            raise AssertionError(f"face_count must be int in {analysis_path}")
        counts["face_records"] += 1

        iqa = analysis.get("iqa_metrics", {}).get("metrics", {}).get("piqe", {})
        finite_number(iqa.get("score"), "piqe.score")
        aesthetic = analysis.get("iqa_metrics", {}).get("metrics", {}).get("aesthetic", {})
        finite_number(aesthetic.get("score"), "aesthetic.score")
        finite_number(aesthetic.get("normalized_score"), "aesthetic.normalized_score")
        if aesthetic.get("direction") != "higher_is_better":
            raise AssertionError(f"aesthetic.direction must be higher_is_better in {analysis_path}")
        if aesthetic.get("clip_head") != "vit_b_32":
            raise AssertionError(f"aesthetic.clip_head must be vit_b_32 in {analysis_path}")
        if not aesthetic.get("device"):
            raise AssertionError(f"aesthetic.device missing in {analysis_path}")
        if not isinstance(aesthetic.get("batch_size"), int) or aesthetic.get("batch_size") < 1:
            raise AssertionError(f"aesthetic.batch_size must be positive int in {analysis_path}")
        counts["iqa_records"] += 1

        if record.get("status", {}).get("overall") == "success":
            counts["status_success_records"] += 1

    if summary.get("total_photos") != len(manifest):
        raise AssertionError(f"summary total_photos mismatch: {summary.get('total_photos')} != {len(manifest)}")
    if task_state.get("totals", {}).get("discovered") != len(manifest):
        raise AssertionError("task_state discovered count does not match manifest")

    return {
        "status": "success",
        "folder": str(folder),
        "cache_dir": str(cache),
        "counts": counts,
        "summary_status": summary.get("status"),
        "task_status": task_state.get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Cullary Phase 1 outputs")
    parser.add_argument("folder", help="Photo folder containing .cullary")
    args = parser.parse_args()
    try:
        result = verify_folder(Path(args.folder).expanduser().resolve())
    except AssertionError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
