from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def laplacian_var(gray: Any) -> float:
    import cv2

    return float(cv2.Laplacian(gray, cv2.CV_64F).var()) if getattr(gray, "size", 0) else 0.0


def tenengrad(gray: Any) -> float:
    import cv2
    import numpy as np

    if gray.size == 0:
        return 0.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy))


def edge_density(gray: Any) -> float:
    import cv2
    import numpy as np

    if gray.size == 0:
        return 0.0
    median = float(np.median(gray))
    edges = cv2.Canny(gray, int(max(0, 0.66 * median)), int(min(255, 1.33 * median)))
    return float(np.count_nonzero(edges) / edges.size)


def motion_blur_proxy(gray: Any) -> dict[str, float]:
    import cv2
    import numpy as np

    if gray.size == 0:
        return {"gradient_anisotropy": 0.0, "dominant_angle_deg": 0.0}
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gxx = float(np.mean(gx * gx)); gyy = float(np.mean(gy * gy)); gxy = float(np.mean(gx * gy))
    trace = gxx + gyy
    if trace <= 1e-9:
        return {"gradient_anisotropy": 0.0, "dominant_angle_deg": 0.0}
    diff = gxx - gyy
    discr = math.sqrt(diff * diff + 4.0 * gxy * gxy)
    l1 = (trace + discr) / 2.0; l2 = (trace - discr) / 2.0
    return {"gradient_anisotropy": round(float((l1 - l2) / max(l1 + l2, 1e-9)), 6), "dominant_angle_deg": round(float(0.5 * math.degrees(math.atan2(2.0 * gxy, diff))), 2)}


def color_cast_metrics(rgb: Any) -> dict[str, Any]:
    import numpy as np

    arr = rgb.astype(np.float32)
    means = arr.reshape(-1, 3).mean(axis=0)
    global_mean = float(means.mean())
    deviations = means - global_mean
    return {
        "rgb_mean": [round(float(v), 3) for v in means],
        "color_cast_rgb_deviation": [round(float(v), 3) for v in deviations],
        "color_cast_strength": round(float(np.linalg.norm(deviations) / 255.0), 6),
        "white_balance_deviation": round(float((means.max() - means.min()) / max(global_mean, 1e-6)), 6),
    }


def estimate_noise_proxy(gray: Any) -> float:
    import cv2
    import numpy as np

    if gray.size == 0:
        return 0.0
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray.astype(np.float32) - blur.astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)
    mask = grad <= np.percentile(grad, 30)
    return float(np.std(residual[mask] if np.any(mask) else residual) / 255.0)


def compute_image_metrics(path: Path, max_side: int) -> dict[str, Any]:
    import cv2
    import numpy as np

    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return {"status": "failed", "error": "cv2.imread failed"}
    h0, w0 = bgr.shape[:2]
    scale = min(1.0, max_side / max(h0, w0))
    bgr_work = cv2.resize(bgr, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else bgr
    h, w = bgr_work.shape[:2]
    rgb = cv2.cvtColor(bgr_work, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(bgr_work, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr_work, cv2.COLOR_BGR2HSV)
    gray_f = gray.astype(np.float32)
    p01, p05, p50, p95, p99 = [float(v) for v in np.percentile(gray_f, [1, 5, 50, 95, 99])]
    cx0, cy0, cx1, cy1 = int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75)
    center_gray = gray[cy0:cy1, cx0:cx1]
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    orientation = "landscape" if w > h * 1.1 else "portrait" if h > w * 1.1 else "squareish"
    metrics = {
        "input": {"max_side": max_side, "analysis_width": w, "analysis_height": h, "scale": round(scale, 6)},
        "exposure": {
            "brightness_mean": round(float(gray_f.mean()), 4), "brightness_median": round(p50, 4),
            "brightness_p01": round(p01, 4), "brightness_p05": round(p05, 4), "brightness_p95": round(p95, 4), "brightness_p99": round(p99, 4),
            "shadow_clip_ratio": round(float(np.count_nonzero(gray <= 4) / gray.size), 6),
            "highlight_clip_ratio": round(float(np.count_nonzero(gray >= 251) / gray.size), 6),
            "dynamic_range_p05_p95": round(float((p95 - p05) / 255.0), 6),
        },
        "contrast": {"contrast_std_ratio": round(float(gray_f.std() / 255.0), 6)},
        "color": {
            "saturation_mean": round(float(sat.mean() / 255.0), 6), "saturation_median": round(float(np.median(sat) / 255.0), 6),
            "saturation_clip_ratio": round(float(np.count_nonzero(sat >= 250) / sat.size), 6), "value_mean": round(float(val.mean() / 255.0), 6),
            **color_cast_metrics(rgb),
        },
        "sharpness": {
            "laplacian_var": round(laplacian_var(gray), 4), "tenengrad": round(tenengrad(gray), 4), "edge_density": round(edge_density(gray), 6),
            "center_laplacian_var": round(laplacian_var(center_gray), 4), "center_tenengrad": round(tenengrad(center_gray), 4),
            "center_sharpness_ratio": round(float((laplacian_var(center_gray) + 1e-6) / (laplacian_var(gray) + 1e-6)), 6),
        },
        "composition": {"aspect_ratio": round(float(w0 / h0), 6), "orientation": orientation, "center_brightness_mean": round(float(center_gray.mean()), 4), "center_brightness_delta": round(float(center_gray.mean() - gray_f.mean()), 4)},
        "experimental": {"noise_proxy": round(estimate_noise_proxy(gray), 6), **motion_blur_proxy(gray)},
    }
    return {"status": "success", "image_metrics": metrics}
