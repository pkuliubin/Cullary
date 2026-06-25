#!/usr/bin/env python3
"""Benchmark LAION aesthetic predictor on local Cullary previews.

This uses the tiny LAION linear head on top of local CLIP image features. The
CLIP encoder dominates runtime; the aesthetic head is negligible.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Any

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
import torch.nn as nn
from PIL import Image
from transformers import CLIPModel, CLIPProcessor


HEAD_URLS = {
    "vit_b_32": "https://raw.githubusercontent.com/LAION-AI/aesthetic-predictor/main/sa_0_4_vit_b_32_linear.pth",
    "vit_l_14": "https://raw.githubusercontent.com/LAION-AI/aesthetic-predictor/main/sa_0_4_vit_l_14_linear.pth",
}

CLIP_HEADS = {
    "vit_b_32": {
        "clip_model": "openai/clip-vit-base-patch32",
        "clip_model_dir": "~/.cullary/models/hf-direct/openai__clip-vit-base-patch32",
        "head_path": "~/.cullary/models/laion-aesthetic/sa_0_4_vit_b_32_linear.pth",
        "embedding_dim": 512,
    },
    "vit_l_14": {
        "clip_model": "openai/clip-vit-large-patch14",
        "clip_model_dir": "~/.cullary/models/hf-direct/openai__clip-vit-large-patch14",
        "head_path": "~/.cullary/models/laion-aesthetic/sa_0_4_vit_l_14_linear.pth",
        "embedding_dim": 768,
    },
}


def now_ms() -> float:
    return time.perf_counter() * 1000


def sync_device(device: torch.device) -> None:
    if device.type == "mps":
        torch.mps.synchronize()
    elif device.type == "cuda":
        torch.cuda.synchronize(device)


def resolve_devices(requested: list[str]) -> list[str]:
    devices: list[str] = []
    for name in requested:
        if name == "auto":
            if torch.backends.mps.is_available():
                name = "mps"
            elif torch.cuda.is_available():
                name = "cuda"
            else:
                name = "cpu"
        if name == "mps" and not torch.backends.mps.is_available():
            print("skip mps: torch.backends.mps.is_available() is false", flush=True)
            continue
        if name == "cuda" and not torch.cuda.is_available():
            print("skip cuda: torch.cuda.is_available() is false", flush=True)
            continue
        if name not in devices:
            devices.append(name)
    return devices or ["cpu"]


def download_head(path: Path, clip_head: str) -> None:
    url = HEAD_URLS[clip_head]
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=30) as response:
        path.write_bytes(response.read())


def load_images(preview_dir: Path, count: int) -> tuple[list[Image.Image], list[str]]:
    paths = sorted(preview_dir.glob("*.jpg"))[:count]
    if not paths:
        raise SystemExit(f"No preview jpg found under {preview_dir}")
    images = [Image.open(path).convert("RGB") for path in paths]
    return images, [str(path) for path in paths]


def load_clip_and_head(model_dir: Path, head_path: Path, embedding_dim: int, device: torch.device) -> tuple[Any, Any, nn.Module, float]:
    if not model_dir.exists():
        raise SystemExit(f"Missing CLIP model directory: {model_dir}")
    if not head_path.exists():
        raise SystemExit(
            f"Missing aesthetic head: {head_path}\n"
            "Run with --download-head, or download sa_0_4_vit_b_32_linear.pth there."
        )
    start = now_ms()
    processor = CLIPProcessor.from_pretrained(str(model_dir), local_files_only=True)
    clip_model = CLIPModel.from_pretrained(str(model_dir), local_files_only=True)
    head = nn.Linear(embedding_dim, 1)
    state = torch.load(head_path, map_location="cpu")
    head.load_state_dict(state)
    clip_model.eval().to(device)
    head.eval().to(device)
    sync_device(device)
    return processor, clip_model, head, now_ms() - start


def score_batch(processor: Any, clip_model: Any, head: nn.Module, images: list[Image.Image], device: torch.device) -> torch.Tensor:
    inputs = processor(images=images, return_tensors="pt")
    inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}
    with torch.inference_mode():
        features = clip_model.get_image_features(**inputs)
        features = torch.nn.functional.normalize(features, p=2, dim=-1)
        scores = head(features).flatten()
    sync_device(device)
    return scores.detach().cpu()


def benchmark_batch_size(
    processor: Any,
    clip_model: Any,
    head: nn.Module,
    images: list[Image.Image],
    batch_size: int,
    runs: int,
    warmup: int,
    device: torch.device,
) -> dict[str, Any]:
    batches = [images[idx : idx + batch_size] for idx in range(0, len(images), batch_size)]
    for _ in range(warmup):
        for batch in batches:
            _ = score_batch(processor, clip_model, head, batch, device)
    times = []
    score_values: list[float] = []
    image_count = 0
    for _ in range(runs):
        start = now_ms()
        score_values = []
        image_count = 0
        for batch in batches:
            out = score_batch(processor, clip_model, head, batch, device)
            image_count += int(out.shape[0])
            score_values.extend(float(v) for v in out)
        times.append(now_ms() - start)
    mean_ms = statistics.mean(times)
    return {
        "batch_size": batch_size,
        "runs": runs,
        "batches_per_run": len(batches),
        "images_per_run": image_count,
        "score": {
            "mean": round(statistics.mean(score_values), 4),
            "min": round(min(score_values), 4),
            "max": round(max(score_values), 4),
            "sample": [round(v, 4) for v in score_values[:8]],
        },
        "total_ms": {
            "mean": round(mean_ms, 2),
            "median": round(statistics.median(times), 2),
            "min": round(min(times), 2),
            "max": round(max(times), 2),
        },
        "per_image_ms_mean": round(mean_ms / max(image_count, 1), 2),
        "images_per_second_mean": round(image_count / max(mean_ms / 1000.0, 1e-9), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark LAION aesthetic predictor")
    parser.add_argument("--preview-dir", default="/Users/liubin/Desktop/TestImage/.cullary/previews")
    parser.add_argument("--clip-head", default="vit_b_32", choices=CLIP_HEADS.keys())
    parser.add_argument("--clip-model-dir", default=None)
    parser.add_argument("--head-path", default=None)
    parser.add_argument("--download-head", action="store_true")
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--devices", nargs="*", default=["cpu", "mps"], choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--batch-sizes", nargs="*", type=int, default=[1, 2, 4, 8, 16])
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", default="cache/aesthetic_predictor_benchmark.json")
    args = parser.parse_args()

    spec = CLIP_HEADS[args.clip_head]
    clip_model_dir = Path(args.clip_model_dir or spec["clip_model_dir"]).expanduser().resolve()
    head_path = Path(args.head_path or spec["head_path"]).expanduser().resolve()
    if args.download_head and not head_path.exists():
        print(f"downloading aesthetic head to {head_path}...", flush=True)
        download_head(head_path, args.clip_head)

    images, paths = load_images(Path(args.preview_dir).expanduser().resolve(), args.count)
    devices = resolve_devices(args.devices)
    results: dict[str, Any] = {
        "status": "success",
        "model": "laion-aesthetic-predictor-v1",
        "clip_head": args.clip_head,
        "clip_model": spec["clip_model"],
        "clip_model_dir": str(clip_model_dir),
        "head_path": str(head_path),
        "image_count": len(images),
        "preview_paths_sample": paths[:5],
        "torch": {
            "version": torch.__version__,
            "mps_built": bool(torch.backends.mps.is_built()),
            "mps_available": bool(torch.backends.mps.is_available()),
            "cuda_available": bool(torch.cuda.is_available()),
        },
        "devices": {},
    }
    for device_name in devices:
        device = torch.device(device_name)
        print(f"loading CLIP + aesthetic head on {device_name}...", flush=True)
        processor, clip_model, head, load_ms = load_clip_and_head(
            clip_model_dir,
            head_path,
            int(spec["embedding_dim"]),
            device,
        )
        params = sum(p.numel() for p in clip_model.parameters()) + sum(p.numel() for p in head.parameters())
        device_result = {
            "parameter_millions": round(params / 1_000_000, 3),
            "head_parameters": sum(p.numel() for p in head.parameters()),
            "load_ms": round(load_ms, 2),
            "batch_results": [],
        }
        for batch_size in args.batch_sizes:
            print(f"benchmarking device={device_name} batch_size={batch_size}...", flush=True)
            try:
                device_result["batch_results"].append(
                    benchmark_batch_size(processor, clip_model, head, images, batch_size, args.runs, args.warmup, device)
                )
            except Exception as exc:
                device_result["batch_results"].append({
                    "batch_size": batch_size,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
        results["devices"][device_name] = device_result
        del clip_model, head
        if device.type == "mps":
            torch.mps.empty_cache()
        elif device.type == "cuda":
            torch.cuda.empty_cache()

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Benchmark written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
