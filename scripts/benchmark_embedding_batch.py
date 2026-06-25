#!/usr/bin/env python3
"""Benchmark embedding batch inference on cached Cullary previews."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor, SiglipVisionModel


MODEL_SPECS = {
    "clip-vit-base-patch32": {"path": "openai__clip-vit-base-patch32", "kind": "clip"},
    "dinov2-small": {"path": "facebook__dinov2-small", "kind": "vision"},
    "dinov2-base": {"path": "facebook__dinov2-base", "kind": "vision"},
    "siglip-base-patch16-224": {"path": "google__siglip-base-patch16-224", "kind": "siglip_vision"},
}


def now_ms() -> float:
    return time.perf_counter() * 1000


def load_images(preview_dir: Path, count: int) -> tuple[list[Image.Image], list[str]]:
    paths = sorted(preview_dir.glob("*.jpg"))[:count]
    if not paths:
        raise SystemExit(f"No preview jpg found under {preview_dir}")
    images = [Image.open(path).convert("RGB") for path in paths]
    return images, [str(path) for path in paths]


def load_model(model_name: str, models_dir: Path) -> tuple[Any, Any, str, float]:
    spec = MODEL_SPECS[model_name]
    path = models_dir / spec["path"]
    if not path.exists():
        raise SystemExit(f"Missing model path: {path}")
    start = now_ms()
    if spec["kind"] == "clip":
        processor = CLIPProcessor.from_pretrained(str(path), local_files_only=True)
        model = CLIPModel.from_pretrained(str(path), local_files_only=True)
    elif spec["kind"] == "siglip_vision":
        processor = AutoImageProcessor.from_pretrained(str(path), local_files_only=True)
        model = SiglipVisionModel.from_pretrained(str(path), local_files_only=True)
    else:
        processor = AutoImageProcessor.from_pretrained(str(path), local_files_only=True)
        model = AutoModel.from_pretrained(str(path), local_files_only=True)
    model.eval()
    return processor, model, spec["kind"], now_ms() - start


def embed_batch(kind: str, processor: Any, model: Any, images: list[Image.Image]) -> torch.Tensor:
    inputs = processor(images=images, return_tensors="pt")
    with torch.inference_mode():
        if kind == "clip" and hasattr(model, "get_image_features"):
            embedding = model.get_image_features(**inputs)
        else:
            outputs = model(**inputs)
            if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                embedding = outputs.pooler_output
            else:
                embedding = outputs.last_hidden_state.mean(dim=1)
        return torch.nn.functional.normalize(embedding, p=2, dim=-1)


def benchmark_batch_size(kind: str, processor: Any, model: Any, images: list[Image.Image], batch_size: int, runs: int, warmup: int) -> dict[str, Any]:
    batches = [images[idx : idx + batch_size] for idx in range(0, len(images), batch_size)]
    for _ in range(warmup):
        for batch in batches:
            _ = embed_batch(kind, processor, model, batch)
    times = []
    vector_count = 0
    last_shape: list[int] | None = None
    for _ in range(runs):
        start = now_ms()
        vector_count = 0
        for batch in batches:
            out = embed_batch(kind, processor, model, batch)
            vector_count += int(out.shape[0])
            last_shape = list(out.shape)
        times.append(now_ms() - start)
    mean_ms = statistics.mean(times)
    return {
        "batch_size": batch_size,
        "runs": runs,
        "batches_per_run": len(batches),
        "vectors_per_run": vector_count,
        "last_batch_shape": last_shape,
        "total_ms": {
            "mean": round(mean_ms, 2),
            "median": round(statistics.median(times), 2),
            "min": round(min(times), 2),
            "max": round(max(times), 2),
        },
        "per_image_ms_mean": round(mean_ms / max(vector_count, 1), 2),
        "images_per_second_mean": round(vector_count / max(mean_ms / 1000.0, 1e-9), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark embedding batch sizes")
    parser.add_argument("--preview-dir", default="/Users/liubin/Desktop/TestImage/.cullary/previews")
    parser.add_argument("--models-dir", default="~/.cullary/models/hf-direct")
    parser.add_argument("--model", default="dinov2-small", choices=MODEL_SPECS.keys())
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--batch-sizes", nargs="*", type=int, default=[1, 2, 4, 8, 16])
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", default="cache/embedding_batch_benchmark.json")
    args = parser.parse_args()

    images, paths = load_images(Path(args.preview_dir).expanduser().resolve(), args.count)
    processor, model, kind, load_ms = load_model(args.model, Path(args.models_dir).expanduser().resolve())
    params = sum(p.numel() for p in model.parameters())
    results = {
        "status": "success",
        "model": args.model,
        "kind": kind,
        "parameter_millions": round(params / 1_000_000, 3),
        "load_ms": round(load_ms, 2),
        "image_count": len(images),
        "preview_paths_sample": paths[:5],
        "torch": {
            "version": torch.__version__,
            "device": "cpu",
            "mps_available": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
        },
        "batch_results": [],
    }
    for batch_size in args.batch_sizes:
        print(f"benchmarking {args.model} batch_size={batch_size}...", flush=True)
        results["batch_results"].append(benchmark_batch_size(kind, processor, model, images, batch_size, args.runs, args.warmup))

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Benchmark written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
