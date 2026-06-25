from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2
except Exception:  # pragma: no cover - optional speedup
    cv2 = None


class PersonMaskAnalyzer:
    def __init__(self, models_dir: Path, config: dict[str, Any]) -> None:
        self.models_dir = models_dir
        self.config = config
        self._segmenter: Any | None = None
        self._mp: Any | None = None

    def analyze(
        self,
        preview_path: Path,
        face_metrics: dict[str, Any],
        *,
        mask_path: Path,
        enhanced_mask_path: Path,
        background_path: Path,
        foreground_path: Path,
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        if not self.config.get("enabled", True):
            return {"enabled": False, "__status": "skipped", "reason": "disabled"}, None, None
        if int(face_metrics.get("face_count", 0) or 0) <= 0:
            return {"__status": "skipped", "reason": "no_face_detected"}, None, None
        model_path = self.model_path()
        if not model_path.exists():
            return None, f"person segmentation model missing: {model_path}", None
        segmenter = self._load_segmenter(model_path)
        if segmenter is None or self._mp is None:
            return None, "failed to create MediaPipe image segmenter", None

        start = time.perf_counter()
        mp_image = self._mp.Image.create_from_file(str(preview_path))
        result = segmenter.segment(mp_image)
        mask = extract_person_mask(result, float(self.config.get("threshold", 0.5)))
        segmentation_ms = int((time.perf_counter() - start) * 1000)

        fill_start = time.perf_counter()
        output = save_person_outputs(
            preview_path,
            mask,
            mask_path=mask_path,
            enhanced_mask_path=enhanced_mask_path,
            background_path=background_path,
            foreground_path=foreground_path,
            dilate_px=int(self.config.get("dilate_px", 32)),
            feather_px=int(self.config.get("feather_px", 18)),
            enhanced_blur_radius=int(self.config.get("enhanced_blur_radius", 120)),
        )
        output.update({
            "status": "success",
            "model": "mediapipe_selfie_segmenter",
            "model_path": str(model_path),
            "segmentation_duration_ms": segmentation_ms,
            "fill_duration_ms": int((time.perf_counter() - fill_start) * 1000),
        })
        return output, None, str(background_path)

    def model_path(self) -> Path:
        path = Path(self.config.get("model_path", "mediapipe/selfie_segmenter.tflite")).expanduser()
        return path if path.is_absolute() else self.models_dir / path

    def _load_segmenter(self, model_path: Path) -> Any | None:
        if self._segmenter is not None:
            return self._segmenter
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except Exception:
            return None
        base_options = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.ImageSegmenterOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            output_category_mask=True,
            output_confidence_masks=True,
        )
        self._segmenter = vision.ImageSegmenter.create_from_options(options)
        self._mp = mp
        return self._segmenter


def extract_person_mask(result: Any, threshold: float) -> np.ndarray:
    if getattr(result, "confidence_masks", None):
        arrays = [np.squeeze(m.numpy_view().copy().astype("float32")) for m in result.confidence_masks]
        if len(arrays) == 1:
            return arrays[0] >= threshold
        stacked = np.stack(arrays, axis=0)
        labels = np.argmax(stacked, axis=0)
        return labels != 0
    if getattr(result, "category_mask", None) is not None:
        return np.squeeze(result.category_mask.numpy_view().copy()) != 0
    raise RuntimeError("segmentation result has neither confidence_masks nor category_mask")


def save_person_outputs(
    preview_path: Path,
    mask: np.ndarray,
    *,
    mask_path: Path,
    enhanced_mask_path: Path,
    background_path: Path,
    foreground_path: Path,
    dilate_px: int,
    feather_px: int,
    enhanced_blur_radius: int,
) -> dict[str, Any]:
    mask = np.squeeze(mask)
    if mask.ndim != 2:
        raise ValueError(f"expected 2D mask, got shape={mask.shape}")
    image = Image.open(preview_path).convert("RGB")
    if mask.shape != (image.height, image.width):
        mask_img = Image.fromarray(mask.astype("uint8") * 255, mode="L").resize(image.size, Image.Resampling.BILINEAR)
        mask = np.array(mask_img) >= 128
    mask_img = Image.fromarray(mask.astype("uint8") * 255, mode="L")
    enhanced_mask = build_enhanced_mask(mask_img, dilate_px=dilate_px, feather_px=feather_px)
    large_blur = build_large_blur(image, enhanced_blur_radius)
    background = Image.composite(large_blur, image, enhanced_mask)
    foreground = build_foreground_image(image, enhanced_mask)

    for path in [mask_path, enhanced_mask_path, background_path, foreground_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
    mask_img.save(mask_path)
    enhanced_mask.save(enhanced_mask_path)
    background.save(background_path, quality=92)
    foreground.save(foreground_path, quality=92)
    enhanced_coverage = float(np.array(enhanced_mask, dtype=np.float32).mean() / 255.0)
    return {
        "foreground_area_ratio": round(float(mask.mean()), 6),
        "foreground_enhanced_area_ratio": round(enhanced_coverage, 6),
        "mask_path": str(mask_path),
        "enhanced_mask_path": str(enhanced_mask_path),
        "background_fill_path": str(background_path),
        "foreground_path": str(foreground_path),
        "input": {"width": image.width, "height": image.height},
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
        size = max(3, dilate_px * 2 + 1)
        if size % 2 == 0:
            size += 1
        result = result.filter(ImageFilter.MaxFilter(size=size))
    if feather_px > 0:
        result = result.filter(ImageFilter.GaussianBlur(radius=feather_px))
    return result


def build_large_blur(image: Image.Image, radius: int) -> Image.Image:
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


def build_foreground_image(image: Image.Image, mask_img: Image.Image) -> Image.Image:
    mask = np.array(mask_img, dtype=np.uint8)
    ys, xs = np.where(mask > 16)
    if len(xs) == 0 or len(ys) == 0:
        return image.copy()
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    margin = int(max(x1 - x0, y1 - y0) * 0.08)
    x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
    x1, y1 = min(image.width, x1 + margin), min(image.height, y1 + margin)
    crop = image.crop((x0, y0, x1, y1))
    crop_mask = mask_img.crop((x0, y0, x1, y1))
    gray = Image.new("RGB", crop.size, (128, 128, 128))
    return Image.composite(crop, gray, crop_mask)
