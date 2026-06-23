#!/usr/bin/env python3
"""Benchmark local embedding model candidates on one cached preview image."""

from __future__ import annotations

import argparse
import json
import math
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

DEFAULT_CACHE = Path(".cullary_cache")
DEFAULT_MODELS_DIR = DEFAULT_CACHE / "models" / "hf-direct"

MODEL_SPECS = {
    "clip-vit-base-patch32": {
        "path": "openai__clip-vit-base-patch32",
        "kind": "clip",
    },
    "dinov2-small": {
        "path": "facebook__dinov2-small",
        "kind": "vision",
    },
    "dinov2-base": {
        "path": "facebook__dinov2-base",
        "kind": "vision",
    },
    "siglip-base-patch16-224": {
        "path": "google__siglip-base-patch16-224",
        "kind": "siglip_vision",
    },
}


def now_ms() -> float:
    return time.perf_counter() * 1000


def read_manifest(cache_dir: Path) -> list[dict[str, Any]]:
    path = cache_dir / "manifest.jsonl"
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def choose_preview(cache_dir: Path, source_id: str | None, source_path: str | None) -> tuple[Path, dict[str, Any]]:
    records = read_manifest(cache_dir)
    candidates = []
    for record in records:
        preview = record.get("preview_path")
        if not preview or not Path(preview).exists():
            continue
        if source_id and record.get("source_id") != source_id:
            continue
        if source_path and record.get("source", {}).get("path") != source_path:
            continue
        candidates.append(record)
    if not candidates:
        raise SystemExit("No matching cached preview found. Run scripts/preprocess.py first.")
    record = candidates[0]
    return Path(record["preview_path"]), record


def tensor_summary(tensor: torch.Tensor, limit: int = 8) -> dict[str, Any]:
    flat = tensor.detach().float().cpu().flatten()
    sample = [round(float(x), 6) for x in flat[:limit]]
    norm = float(torch.linalg.vector_norm(flat).item())
    mean = float(flat.mean().item())
    std = float(flat.std(unbiased=False).item()) if flat.numel() > 1 else 0.0
    min_v = float(flat.min().item())
    max_v = float(flat.max().item())
    finite_ratio = float(torch.isfinite(flat).float().mean().item())
    return {
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "numel": int(flat.numel()),
        "l2_norm": norm,
        "mean": mean,
        "std": std,
        "min": min_v,
        "max": max_v,
        "finite_ratio": finite_ratio,
        "sample_first_values": sample,
    }


def load_model(name: str, path: Path, kind: str) -> tuple[Any, Any, float]:
    start = now_ms()
    if kind == "clip":
        processor = CLIPProcessor.from_pretrained(str(path), local_files_only=True)
        model = CLIPModel.from_pretrained(str(path), local_files_only=True)
    elif kind == "siglip_vision":
        processor = AutoImageProcessor.from_pretrained(str(path), local_files_only=True)
        model = SiglipVisionModel.from_pretrained(str(path), local_files_only=True)
    else:
        processor = AutoImageProcessor.from_pretrained(str(path), local_files_only=True)
        model = AutoModel.from_pretrained(str(path), local_files_only=True)
    model.eval()
    return processor, model, now_ms() - start


def embed_once(kind: str, processor: Any, model: Any, image: Image.Image) -> torch.Tensor:
    inputs = processor(images=image, return_tensors="pt")
    with torch.inference_mode():
        if kind == "clip" and hasattr(model, "get_image_features"):
            embedding = model.get_image_features(**inputs)
        else:
            outputs = model(**inputs)
            if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                embedding = outputs.pooler_output
            else:
                embedding = outputs.last_hidden_state.mean(dim=1)
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=-1)
    return embedding


def benchmark_model(name: str, model_dir: Path, image: Image.Image, warmup: int, runs: int) -> dict[str, Any]:
    spec = MODEL_SPECS[name]
    path = model_dir / spec["path"]
    if not path.exists():
        return {"status": "missing", "model_path": str(path)}

    try:
        processor, model, load_ms = load_model(name, path, spec["kind"])
        params = sum(p.numel() for p in model.parameters())
        first_start = now_ms()
        first_embedding = embed_once(spec["kind"], processor, model, image)
        first_infer_ms = now_ms() - first_start

        for _ in range(warmup):
            _ = embed_once(spec["kind"], processor, model, image)

        times = []
        last_embedding = first_embedding
        for _ in range(runs):
            start = now_ms()
            last_embedding = embed_once(spec["kind"], processor, model, image)
            times.append(now_ms() - start)

        del processor, model
        return {
            "status": "success",
            "model_path": str(path),
            "kind": spec["kind"],
            "parameter_count": params,
            "parameter_millions": round(params / 1_000_000, 3),
            "load_ms": round(load_ms, 2),
            "first_inference_ms": round(first_infer_ms, 2),
            "warm_inference_ms": {
                "runs": runs,
                "mean": round(statistics.mean(times), 2),
                "median": round(statistics.median(times), 2),
                "min": round(min(times), 2),
                "max": round(max(times), 2),
            },
            "embedding": tensor_summary(last_embedding),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "model_path": str(path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local Cullary embedding candidates")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--models-dir", default=str(DEFAULT_MODELS_DIR))
    parser.add_argument("--source-id")
    parser.add_argument("--source-path")
    parser.add_argument("--models", nargs="*", default=list(MODEL_SPECS.keys()), choices=list(MODEL_SPECS.keys()))
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_CACHE / "embedding_benchmark.json"))
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir).expanduser().resolve()
    model_dir = Path(args.models_dir).expanduser().resolve()
    preview_path, record = choose_preview(cache_dir, args.source_id, args.source_path)
    image = Image.open(preview_path).convert("RGB")

    results = {
        "source": record.get("source"),
        "source_id": record.get("source_id"),
        "preview_path": str(preview_path),
        "preview_image": {"width": image.width, "height": image.height},
        "torch": {
            "version": torch.__version__,
            "device": "cpu",
            "mps_available": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
        },
        "benchmark": {
            "warmup": args.warmup,
            "runs": args.runs,
            "models": {},
        },
    }

    for model_name in args.models:
        print(f"benchmarking {model_name}...", flush=True)
        results["benchmark"]["models"][model_name] = benchmark_model(model_name, model_dir, image, args.warmup, args.runs)

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Benchmark written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
