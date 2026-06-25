#!/usr/bin/env python3
"""Benchmark MediaPipe Tasks image segmentation on selected Cullary previews."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2
except Exception:  # pragma: no cover - optional speedup
    cv2 = None

DEFAULT_FILES = [
    "B0007059.3FR",
    "B0007111.3FR",
    "B0007120.3FR",
    "B0007277.3FR",
    "B0007278.3FR",
    "B0007603.3FR",
    "B0007616.3FR",
    "B0010413.3FR",
    "B0010357.3FR",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve(folder: Path, maybe_relative: str) -> Path:
    path = Path(maybe_relative)
    return path if path.is_absolute() else folder / path


def find_preview_records(folder: Path, file_names: list[str]) -> list[dict[str, Any]]:
    manifest_path = folder / ".cullary" / "manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    wanted = set(file_names)
    records = []
    for record in load_jsonl(manifest_path):
        if record.get("source", {}).get("file_name") in wanted:
            records.append(record)
    found = {r.get("source", {}).get("file_name") for r in records}
    missing = sorted(wanted - found)
    if missing:
        print(json.dumps({"warning": "missing files in manifest", "files": missing}, ensure_ascii=False))
    return sorted(records, key=lambda r: file_names.index(r.get("source", {}).get("file_name")))


def create_segmenter(model_path: Path):
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    base_options = python.BaseOptions(model_asset_path=str(model_path))
    options = vision.ImageSegmenterOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        output_category_mask=True,
        output_confidence_masks=True,
    )
    return vision.ImageSegmenter.create_from_options(options), mp


def extract_person_mask(result: Any, threshold: float) -> np.ndarray:
    if getattr(result, "confidence_masks", None):
        masks = result.confidence_masks
        arrays = [np.squeeze(m.numpy_view().copy().astype("float32")) for m in masks]
        if len(arrays) == 1:
            return arrays[0] >= threshold
        stacked = np.stack(arrays, axis=0)
        labels = np.argmax(stacked, axis=0)
        # In common selfie/person segmenters, background is class 0 and person/foreground is non-zero.
        return labels != 0
    if getattr(result, "category_mask", None) is not None:
        category = np.squeeze(result.category_mask.numpy_view().copy())
        return category != 0
    raise RuntimeError("segmentation result has neither confidence_masks nor category_mask")


def save_outputs(
    preview_path: Path,
    out_dir: Path,
    display_id: str,
    mask: np.ndarray,
    *,
    dilate_px: int,
    feather_px: int,
    enhanced_blur_radius: int,
) -> dict[str, Any]:
    mask = np.squeeze(mask)
    if mask.ndim != 2:
        raise ValueError(f"expected 2D mask, got shape={mask.shape}")
    image = Image.open(preview_path).convert("RGB")
    if mask.shape != (image.height, image.width):
        mask_img = Image.fromarray((mask.astype("uint8") * 255), mode="L").resize(image.size, Image.Resampling.BILINEAR)
        mask = np.array(mask_img) >= 128
    mask_u8 = mask.astype("uint8") * 255
    mask_img = Image.fromarray(mask_u8, mode="L")

    overlay = image.copy()
    red = Image.new("RGB", image.size, (255, 40, 20))
    overlay = Image.composite(red, overlay, mask_img.point(lambda v: int(v * 0.45)))

    simple_blur = image.filter(ImageFilter.GaussianBlur(radius=max(12, min(image.size) // 25)))
    simple_background = Image.composite(simple_blur, image, mask_img)

    enhanced_mask = build_enhanced_mask(mask_img, dilate_px=dilate_px, feather_px=feather_px)
    large_blur = build_large_blur(image, enhanced_blur_radius)
    enhanced_background = Image.composite(large_blur, image, enhanced_mask)

    mask_path = out_dir / f"{display_id}__mask.png"
    enhanced_mask_path = out_dir / f"{display_id}__mask_enhanced.png"
    overlay_path = out_dir / f"{display_id}__overlay.jpg"
    background_path = out_dir / f"{display_id}__background_fill.jpg"
    enhanced_background_path = out_dir / f"{display_id}__background_fill_enhanced.jpg"
    copy_path = out_dir / f"{display_id}__preview.jpg"
    image.save(copy_path, quality=92)
    mask_img.save(mask_path)
    enhanced_mask.save(enhanced_mask_path)
    overlay.save(overlay_path, quality=92)
    simple_background.save(background_path, quality=92)
    enhanced_background.save(enhanced_background_path, quality=92)

    enhanced_coverage = float(np.array(enhanced_mask, dtype=np.float32).mean() / 255.0)
    return {
        "preview_path": str(copy_path),
        "mask_path": str(mask_path),
        "enhanced_mask_path": str(enhanced_mask_path),
        "overlay_path": str(overlay_path),
        "background_fill_path": str(background_path),
        "background_fill_enhanced_path": str(enhanced_background_path),
        "width": image.width,
        "height": image.height,
        "coverage_ratio": round(float(mask.mean()), 6),
        "enhanced_coverage_ratio": round(enhanced_coverage, 6),
    }


def build_enhanced_mask(mask_img: Image.Image, *, dilate_px: int, feather_px: int) -> Image.Image:
    if cv2 is not None:
        mask = np.array(mask_img.convert("L"), dtype=np.uint8)
        if dilate_px > 0:
            size = max(3, dilate_px * 2 + 1)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
            mask = cv2.dilate(mask, kernel, iterations=1)
        if feather_px > 0:
            ksize = max(3, feather_px * 4 + 1)
            if ksize % 2 == 0:
                ksize += 1
            mask = cv2.GaussianBlur(mask, (ksize, ksize), sigmaX=feather_px)
        return Image.fromarray(mask, mode="L")

    result = mask_img.convert("L")
    if dilate_px > 0:
        # MaxFilter approximates binary dilation; size must be odd.
        size = max(3, dilate_px * 2 + 1)
        if size % 2 == 0:
            size += 1
        result = result.filter(ImageFilter.MaxFilter(size=size))
    if feather_px > 0:
        result = result.filter(ImageFilter.GaussianBlur(radius=feather_px))
    return result


def build_large_blur(image: Image.Image, radius: int) -> Image.Image:
    # Large Pillow GaussianBlur on 1600px previews can take seconds. Downsample first
    # to create a low-frequency background fill that is much faster and sufficient
    # for background embedding probes.
    if radius <= 0:
        return image.copy()
    max_side = max(image.size)
    small_max_side = max(64, min(256, max_side // 8))
    scale = small_max_side / max_side
    small_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    small = image.resize(small_size, Image.Resampling.BILINEAR)
    small_radius = max(2, int(radius * scale))
    small_blur = small.filter(ImageFilter.GaussianBlur(radius=small_radius))
    return small_blur.resize(image.size, Image.Resampling.BICUBIC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark MediaPipe Tasks selfie/person segmentation")
    parser.add_argument("folder", nargs="?", default="/Users/liubin/Desktop/TestImage")
    parser.add_argument("--model", default="~/.cullary/models/mediapipe/selfie_segmenter.tflite")
    parser.add_argument("--files", nargs="*", default=DEFAULT_FILES)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--output", default=None, help="Default: <folder>/.cullary/segmentation_probe")
    parser.add_argument("--dilate-px", type=int, default=32, help="Expand person mask before enhanced background fill")
    parser.add_argument("--feather-px", type=int, default=18, help="Feather enhanced person mask edge")
    parser.add_argument("--enhanced-blur-radius", type=int, default=120, help="Large blur radius for enhanced background fill")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        print(json.dumps({"status": "failed", "error": f"missing model: {model_path}"}, ensure_ascii=False, indent=2))
        return 2
    out_dir = Path(args.output).expanduser().resolve() if args.output else folder / ".cullary" / "segmentation_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    records = find_preview_records(folder, args.files)
    segmenter, mp = create_segmenter(model_path)
    results = []
    try:
        for record in records:
            display_id = record["display_id"]
            preview_path = resolve(folder, record.get("assets", {}).get("preview_path", ""))
            if not preview_path.exists():
                results.append({"display_id": display_id, "status": "failed", "error": f"missing preview: {preview_path}"})
                continue
            start = time.perf_counter()
            mp_image = mp.Image.create_from_file(str(preview_path))
            result = segmenter.segment(mp_image)
            mask = extract_person_mask(result, args.threshold)
            duration_ms = int((time.perf_counter() - start) * 1000)
            fill_start = time.perf_counter()
            output = save_outputs(
                preview_path,
                out_dir,
                display_id,
                mask,
                dilate_px=args.dilate_px,
                feather_px=args.feather_px,
                enhanced_blur_radius=args.enhanced_blur_radius,
            )
            fill_duration_ms = int((time.perf_counter() - fill_start) * 1000)
            results.append({
                "display_id": display_id,
                "source_file": record.get("source", {}).get("file_name"),
                "status": "success",
                "segmentation_duration_ms": duration_ms,
                "fill_duration_ms": fill_duration_ms,
                "duration_ms": duration_ms + fill_duration_ms,
                **output,
            })
    finally:
        segmenter.close()

    summary = {
        "status": "success",
        "model_path": str(model_path),
        "output_dir": str(out_dir),
        "count": len(results),
        "success_count": sum(1 for r in results if r.get("status") == "success"),
        "avg_duration_ms": round(sum(r.get("duration_ms", 0) for r in results if r.get("status") == "success") / max(1, sum(1 for r in results if r.get("status") == "success")), 2),
        "avg_segmentation_duration_ms": round(sum(r.get("segmentation_duration_ms", 0) for r in results if r.get("status") == "success") / max(1, sum(1 for r in results if r.get("status") == "success")), 2),
        "avg_fill_duration_ms": round(sum(r.get("fill_duration_ms", 0) for r in results if r.get("status") == "success") / max(1, sum(1 for r in results if r.get("status") == "success")), 2),
        "enhanced_fill_config": {
            "dilate_px": args.dilate_px,
            "feather_px": args.feather_px,
            "enhanced_blur_radius": args.enhanced_blur_radius,
        },
        "results": results,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
