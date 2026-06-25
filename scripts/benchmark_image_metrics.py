#!/usr/bin/env python3
"""Probe non-model image statistics, blur, and simple composition metrics."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DEFAULT_CACHE = Path('.cullary_cache')


def clamp_box(x0: int, y0: int, x1: int, y1: int, w: int, h: int) -> tuple[int, int, int, int]:
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def laplacian_var(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray.size else 0.0


def tenengrad(gray: np.ndarray) -> float:
    if gray.size == 0:
        return 0.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return float(np.mean(gx * gx + gy * gy))


def edge_density(gray: np.ndarray) -> float:
    if gray.size == 0:
        return 0.0
    median = float(np.median(gray))
    lower = int(max(0, 0.66 * median))
    upper = int(min(255, 1.33 * median))
    edges = cv2.Canny(gray, lower, upper)
    return float(np.count_nonzero(edges) / edges.size)


def motion_blur_proxy(gray: np.ndarray) -> dict[str, float]:
    """Estimate directional blur by gradient anisotropy. Higher anisotropy means more directional texture/blur risk."""
    if gray.size == 0:
        return {'gradient_anisotropy': 0.0, 'dominant_angle_deg': 0.0}
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gxx = float(np.mean(gx * gx))
    gyy = float(np.mean(gy * gy))
    gxy = float(np.mean(gx * gy))
    trace = gxx + gyy
    if trace <= 1e-9:
        return {'gradient_anisotropy': 0.0, 'dominant_angle_deg': 0.0}
    diff = gxx - gyy
    discr = math.sqrt(diff * diff + 4.0 * gxy * gxy)
    l1 = (trace + discr) / 2.0
    l2 = (trace - discr) / 2.0
    anisotropy = (l1 - l2) / max(l1 + l2, 1e-9)
    angle = 0.5 * math.degrees(math.atan2(2.0 * gxy, diff))
    return {'gradient_anisotropy': round(float(anisotropy), 6), 'dominant_angle_deg': round(float(angle), 2)}


def color_cast_metrics(rgb: np.ndarray) -> dict[str, Any]:
    arr = rgb.astype(np.float32)
    means = arr.reshape(-1, 3).mean(axis=0)
    global_mean = float(means.mean())
    deviations = means - global_mean
    cast_strength = float(np.linalg.norm(deviations) / 255.0)
    wb_dev = float((means.max() - means.min()) / max(global_mean, 1e-6))
    return {
        'rgb_mean': [round(float(v), 3) for v in means],
        'color_cast_rgb_deviation': [round(float(v), 3) for v in deviations],
        'color_cast_strength': round(cast_strength, 6),
        'white_balance_deviation': round(wb_dev, 6),
    }


def estimate_noise_proxy(gray: np.ndarray) -> float:
    """Rough high-frequency residual on low-gradient pixels."""
    if gray.size == 0:
        return 0.0
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray.astype(np.float32) - blur.astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)
    threshold = np.percentile(grad, 30)
    mask = grad <= threshold
    if not np.any(mask):
        return float(np.std(residual) / 255.0)
    return float(np.std(residual[mask]) / 255.0)


def analyze_image(path: Path, max_side: int) -> dict[str, Any]:
    start = time.perf_counter()
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return {'preview': str(path), 'status': 'failed', 'error': 'cv2.imread failed'}
    h0, w0 = bgr.shape[:2]
    scale = min(1.0, max_side / max(h0, w0))
    if scale < 1.0:
        bgr_work = cv2.resize(bgr, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
    else:
        bgr_work = bgr
    h, w = bgr_work.shape[:2]
    rgb = cv2.cvtColor(bgr_work, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(bgr_work, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr_work, cv2.COLOR_BGR2HSV)

    gray_f = gray.astype(np.float32)
    p01, p05, p50, p95, p99 = [float(v) for v in np.percentile(gray_f, [1, 5, 50, 95, 99])]
    hist_total = gray.size

    cx0, cy0, cx1, cy1 = clamp_box(int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75), w, h)
    center_gray = gray[cy0:cy1, cx0:cx1]

    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)

    if w > h * 1.1:
        orientation = 'landscape'
    elif h > w * 1.1:
        orientation = 'portrait'
    else:
        orientation = 'squareish'

    metrics = {
        'preview': str(path),
        'status': 'success',
        'source_size': {'width': w0, 'height': h0},
        'analysis_size': {'width': w, 'height': h, 'scale': round(scale, 6)},
        'image_statistics': {
            'brightness_mean': round(float(gray_f.mean()), 4),
            'brightness_median': round(p50, 4),
            'brightness_p01': round(p01, 4),
            'brightness_p05': round(p05, 4),
            'brightness_p95': round(p95, 4),
            'brightness_p99': round(p99, 4),
            'shadow_clip_ratio': round(float(np.count_nonzero(gray <= 4) / hist_total), 6),
            'highlight_clip_ratio': round(float(np.count_nonzero(gray >= 251) / hist_total), 6),
            'contrast_std_ratio': round(float(gray_f.std() / 255.0), 6),
            'dynamic_range_p05_p95': round(float((p95 - p05) / 255.0), 6),
            'saturation_mean': round(float(sat.mean() / 255.0), 6),
            'saturation_median': round(float(np.median(sat) / 255.0), 6),
            'saturation_clip_ratio': round(float(np.count_nonzero(sat >= 250) / sat.size), 6),
            'value_mean': round(float(val.mean() / 255.0), 6),
            'noise_proxy': round(estimate_noise_proxy(gray), 6),
            **color_cast_metrics(rgb),
        },
        'sharpness_blur': {
            'laplacian_var': round(laplacian_var(gray), 4),
            'tenengrad': round(tenengrad(gray), 4),
            'edge_density': round(edge_density(gray), 6),
            'center_laplacian_var': round(laplacian_var(center_gray), 4),
            'center_tenengrad': round(tenengrad(center_gray), 4),
            **motion_blur_proxy(gray),
        },
        'composition': {
            'aspect_ratio': round(float(w0 / h0), 6),
            'orientation': orientation,
            'center_brightness_mean': round(float(center_gray.mean()), 4) if center_gray.size else 0.0,
            'center_brightness_delta': round(float(center_gray.mean() - gray_f.mean()), 4) if center_gray.size else 0.0,
            'center_sharpness_ratio': round(float((laplacian_var(center_gray) + 1e-6) / (laplacian_var(gray) + 1e-6)), 6),
            'rule_of_thirds_points_norm': [[0.3333, 0.3333], [0.6667, 0.3333], [0.3333, 0.6667], [0.6667, 0.6667]],
        },
        'duration_ms': round((time.perf_counter() - start) * 1000, 2),
    }
    return metrics


def summary_for(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in results if r.get('status') == 'success']
    def collect(section: str, key: str) -> list[float]:
        vals = []
        for r in ok:
            v = r.get(section, {}).get(key)
            if isinstance(v, (int, float)):
                vals.append(float(v))
        return vals
    summary: dict[str, Any] = {'total': len(results), 'success': len(ok)}
    for section, keys in {
        'image_statistics': ['brightness_mean', 'shadow_clip_ratio', 'highlight_clip_ratio', 'contrast_std_ratio', 'dynamic_range_p05_p95', 'saturation_mean', 'color_cast_strength', 'white_balance_deviation', 'noise_proxy'],
        'sharpness_blur': ['laplacian_var', 'tenengrad', 'edge_density', 'center_laplacian_var', 'gradient_anisotropy'],
    }.items():
        summary[section] = {}
        for key in keys:
            vals = collect(section, key)
            if vals:
                summary[section][key] = {'mean': round(statistics.mean(vals), 6), 'min': round(min(vals), 6), 'max': round(max(vals), 6)}
    times = [float(r['duration_ms']) for r in ok]
    summary['duration_ms'] = {'mean': round(statistics.mean(times), 2), 'median': round(statistics.median(times), 2), 'max': round(max(times), 2)} if times else None
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-dir', default=str(DEFAULT_CACHE))
    parser.add_argument('--limit', type=int, default=46)
    parser.add_argument('--max-side', type=int, default=1024)
    parser.add_argument('--output', default=str(DEFAULT_CACHE / 'image_metrics_probe.json'))
    args = parser.parse_args()
    previews = sorted((Path(args.cache_dir) / 'previews').glob('*.jpg'))[:args.limit]
    results = []
    for i, p in enumerate(previews, 1):
        print(f'[{i}/{len(previews)}] {p.name}', flush=True)
        results.append(analyze_image(p, args.max_side))
    payload = {'max_side': args.max_side, 'summary': summary_for(results), 'results': results}
    out = Path(args.output)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=2))
    print('written:', out.resolve())
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
