#!/usr/bin/env python3
"""Benchmark cached preview read/decode throughput for Cullary UI planning."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def load_manifest_previews(manifest: Path) -> list[Path]:
    previews: list[Path] = []
    with manifest.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            preview = record.get("preview_path")
            if preview:
                previews.append(Path(preview))
    return previews


def discover_images(path: Path) -> list[Path]:
    if path.is_file() and path.name.endswith(".jsonl"):
        return load_manifest_previews(path)
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    return []


def pct(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round((percentile / 100) * (len(values) - 1))))
    return values[idx]


def maybe_import_pillow() -> Any | None:
    try:
        from PIL import Image

        return Image
    except Exception:
        return None


def bench(paths: list[Path], *, loops: int, decode: bool, resize_edge: int | None) -> dict[str, Any]:
    image_mod = maybe_import_pillow() if decode else None
    if decode and image_mod is None:
        print("Pillow not installed; decode benchmark will be skipped.")

    read_ms: list[float] = []
    decode_ms: list[float] = []
    total_bytes = 0
    failures = 0
    samples = [random.choice(paths) for _ in range(loops)] if paths else []
    started = time.perf_counter()

    for path in samples:
        try:
            t0 = time.perf_counter()
            data = path.read_bytes()
            read_ms.append((time.perf_counter() - t0) * 1000)
            total_bytes += len(data)

            if decode and image_mod is not None:
                import io

                t1 = time.perf_counter()
                with image_mod.open(io.BytesIO(data)) as image:
                    image.load()
                    if resize_edge:
                        image.thumbnail((resize_edge, resize_edge))
                decode_ms.append((time.perf_counter() - t1) * 1000)
        except Exception:
            failures += 1

    elapsed = time.perf_counter() - started
    return {
        "samples": len(samples),
        "unique_files": len(set(paths)),
        "failures": failures,
        "total_mb": round(total_bytes / 1024 / 1024, 2),
        "elapsed_s": round(elapsed, 3),
        "read_mb_s": round((total_bytes / 1024 / 1024) / elapsed, 2) if elapsed else 0,
        "read_ms": summarize_ms(read_ms),
        "decode_ms": summarize_ms(decode_ms) if decode_ms else None,
    }


def summarize_ms(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "avg": round(statistics.mean(values), 2),
        "p50": round(pct(values, 50), 2),
        "p95": round(pct(values, 95), 2),
        "max": round(max(values), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark cached preview image IO/decode speed")
    parser.add_argument("path", help="Preview directory or .cullary_cache/manifest.jsonl")
    parser.add_argument("--loops", type=int, default=500, help="Number of random image reads")
    parser.add_argument("--decode", action="store_true", help="Also decode images with Pillow")
    parser.add_argument("--resize-edge", type=int, default=None, help="Resize decoded image to this long edge")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    paths = [p for p in discover_images(Path(args.path).expanduser()) if p.exists()]
    if not paths:
        print(f"No preview images found under: {args.path}")
        return 2

    result = bench(paths, loops=args.loops, decode=args.decode, resize_edge=args.resize_edge)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
