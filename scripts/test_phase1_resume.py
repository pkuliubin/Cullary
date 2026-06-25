#!/usr/bin/env python3
"""Exercise Phase 1 resume/stale behavior on a tiny generated folder."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = "/opt/anaconda3/envs/hippo/bin/python"


def run(cmd: list[str], *, cwd: Path = REPO, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        print(proc.stdout)
        raise SystemExit(proc.returncode)
    return proc


def make_sample(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for idx, color in enumerate([(180, 60, 40), (40, 140, 210)], start=1):
        image = Image.new("RGB", (800, 600), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 120, 500, 420), outline=(255, 255, 255), width=8)
        draw.text((130, 150), f"Cullary {idx}", fill=(255, 255, 255))
        image.save(folder / f"sample_{idx}.jpg", quality=92)
    (folder / ".DS_Store").write_text("ignored", encoding="utf-8")
    (folder / "partial.crdownload").write_text("ignored", encoding="utf-8")


def load_summary(folder: Path) -> dict:
    return json.loads((folder / ".cullary" / "run_summary.json").read_text(encoding="utf-8"))


def load_manifest(folder: Path) -> list[dict]:
    path = folder / ".cullary" / "manifest.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assert_stage_count(summary: dict, stage: str, status: str, expected: int) -> None:
    actual = summary.get("stage_runtime", {}).get(stage, {}).get(status)
    if actual != expected:
        raise AssertionError(f"{stage}.{status}: expected {expected}, got {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Cullary Phase 1 resume/stale behavior")
    parser.add_argument("--work-dir", default="/private/tmp/cullary-phase1-resume")
    parser.add_argument("--python", default=os.environ.get("PYTHON_BIN", DEFAULT_PYTHON))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    work = Path(args.work_dir).expanduser().resolve()
    if work.exists() and not args.keep:
        shutil.rmtree(work)
    make_sample(work)

    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    cmd = [args.python, "-m", "cullary.preprocessing", str(work)]
    verify = [args.python, "scripts/verify_phase1_outputs.py", str(work)]

    # A stray old cache directory should never be scanned as source photos.
    stray_cache = work / ".cullary_cache" / "previews"
    stray_cache.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 96), (1, 2, 3)).save(stray_cache / "should_not_scan.jpg")

    run(cmd, env=env)
    run(verify)
    first = load_summary(work)
    if first.get("total_photos") != 2:
        raise AssertionError(f"expected 2 photos, got {first.get('total_photos')}")
    for stage in ["metadata", "preview", "thumb", "hash", "image_metrics", "embedding", "face", "iqa"]:
        assert_stage_count(first, stage, "skipped", 0)

    run(cmd, env=env)
    run(verify)
    second = load_summary(work)
    for stage in ["metadata", "preview", "thumb", "hash", "image_metrics", "embedding", "face", "iqa"]:
        assert_stage_count(second, stage, "skipped", 2)

    # Removing one per-photo analysis should cause only that photo to be repaired.
    missing_analysis = work / ".cullary" / "analysis" / "sample_2_JPG" / "analysis.json"
    missing_analysis.unlink()
    run(cmd, env=env)
    run(verify)
    repaired = load_summary(work)
    for stage in ["metadata", "preview", "thumb", "hash", "image_metrics", "embedding", "face", "iqa"]:
        assert_stage_count(repaired, stage, "skipped", 1)
        runtime = repaired.get("stage_runtime", {}).get(stage, {})
        if runtime.get("done") != 2 or runtime.get("failed") != 0:
            raise AssertionError(f"unexpected repair runtime for {stage}: {runtime}")

    target = work / "sample_1.jpg"
    # Ensure mtime changes even on filesystems with coarse timestamp resolution.
    time.sleep(1.1)
    image = Image.open(target).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse((520, 120, 700, 300), fill=(20, 220, 120))
    image.save(target, quality=92)

    run(cmd, env=env)
    run(verify)
    third = load_summary(work)
    for stage in ["metadata", "preview", "thumb", "hash", "image_metrics", "embedding", "face", "iqa"]:
        assert_stage_count(third, stage, "skipped", 1)
        runtime = third.get("stage_runtime", {}).get(stage, {})
        if runtime.get("done") != 2 or runtime.get("failed") != 0:
            raise AssertionError(f"unexpected stale runtime for {stage}: {runtime}")

    metrics_config = work / "image_metrics_config.json"
    config = json.loads((REPO / "config" / "preprocess.default.json").read_text(encoding="utf-8"))
    config["image_metrics"]["max_side"] = 768
    metrics_config.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics_cmd = [args.python, "-m", "cullary.preprocessing", str(work), "--config", str(metrics_config)]
    run(metrics_cmd, env=env)
    run(verify)
    metrics_summary = load_summary(work)
    assert_stage_count(metrics_summary, "image_metrics", "skipped", 0)
    for stage in ["metadata", "preview", "thumb", "hash", "embedding", "face", "iqa"]:
        assert_stage_count(metrics_summary, stage, "skipped", 2)

    # Restore default config before exercising model failure in an isolated cache.
    run(cmd, env=env)
    run(verify)

    bad_config = work / "bad_embedding_config.json"
    config = json.loads((REPO / "config" / "preprocess.default.json").read_text(encoding="utf-8"))
    config["cache"]["dir_name"] = ".cullary_bad_model"
    config["embedding"]["model_path"] = "hf-direct/does-not-exist"
    bad_config.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    bad_cmd = [args.python, "-m", "cullary.preprocessing", str(work), "--config", str(bad_config), "--limit", "1"]
    run(bad_cmd, env=env)
    bad_summary = json.loads((work / ".cullary_bad_model" / "run_summary.json").read_text(encoding="utf-8"))
    if bad_summary.get("status") != "partial_success":
        raise AssertionError(f"bad model run should be partial_success: {bad_summary.get('status')}")
    if bad_summary.get("analyzer_counts", {}).get("embedding", {}).get("failed") != 1:
        raise AssertionError("bad model run should record one embedding failure")
    for stage in ["metadata", "preview", "thumb", "hash", "image_metrics", "face", "iqa"]:
        if bad_summary.get("analyzer_counts", {}).get(stage, {}).get("success") != 1:
            raise AssertionError(f"bad model run should not block {stage}: {bad_summary.get('analyzer_counts', {}).get(stage)}")

    manifest = load_manifest(work)
    if any("should_not_scan" in record["source"]["relative_path"] for record in manifest):
        raise AssertionError("files under .cullary_cache must not be scanned")
    names = sorted(record["display_id"] for record in manifest)
    result = {
        "status": "success",
        "work_dir": str(work),
        "display_ids": names,
        "first_duration_ms": first.get("duration_ms"),
        "cache_hit_duration_ms": second.get("duration_ms"),
        "repair_missing_analysis_duration_ms": repaired.get("duration_ms"),
        "single_file_stale_duration_ms": third.get("duration_ms"),
        "image_metrics_config_duration_ms": metrics_summary.get("duration_ms"),
        "bad_model_status": bad_summary.get("status"),
        "ignored": third.get("ignored"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
