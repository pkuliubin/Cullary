#!/usr/bin/env python3
"""Benchmark face analyzers on cached previews."""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DEFAULT_CACHE = Path('.cullary_cache')


def lap_var(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray.size else 0.0


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in results if r.get('status') == 'success']
    times = [r['duration_ms'] for r in ok]
    return {
        'total': len(results),
        'success': len(ok),
        'with_faces': sum(1 for r in ok if r.get('face_count', 0) > 0),
        'total_faces': sum(r.get('face_count', 0) for r in ok),
        'face_count_distribution': {str(k): sum(1 for r in ok if r.get('face_count') == k) for k in sorted({r.get('face_count', 0) for r in ok})},
        'duration_ms': {
            'mean': round(statistics.mean(times), 2),
            'median': round(statistics.median(times), 2),
            'min': round(min(times), 2),
            'max': round(max(times), 2),
        } if times else None,
        'examples_with_faces': [r for r in ok if r.get('face_count', 0) > 0][:3],
    }


def run_mediapipe(previews: list[Path], max_side: int) -> dict[str, Any]:
    import mediapipe as mp
    detector = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    results = []
    for p in previews:
        img = cv2.imread(str(p))
        if img is None:
            results.append({'preview': str(p), 'status': 'failed', 'error': 'cv2.imread failed'})
            continue
        h, w = img.shape[:2]
        scale = min(1.0, max_side / max(h, w))
        work = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
        rgb = cv2.cvtColor(work, cv2.COLOR_BGR2RGB)
        t = time.perf_counter()
        det = detector.process(rgb)
        ms = (time.perf_counter() - t) * 1000
        faces = []
        if det.detections:
            for d in det.detections:
                box = d.location_data.relative_bounding_box
                x = box.xmin * w
                y = box.ymin * h
                bw = box.width * w
                bh = box.height * h
                x0, y0 = max(0, int(x)), max(0, int(y))
                x1, y1 = min(w, int(x + bw)), min(h, int(y + bh))
                gray = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY) if x1 > x0 and y1 > y0 else np.array([])
                faces.append({
                    'box': {'x': round(x, 1), 'y': round(y, 1), 'w': round(bw, 1), 'h': round(bh, 1)},
                    'score': round(float(d.score[0]), 4) if d.score else None,
                    'area_ratio': round((bw * bh) / (w * h), 6),
                    'sharpness_laplacian_var': round(lap_var(gray), 2),
                })
        results.append({'preview': str(p), 'status': 'success', 'width': w, 'height': h, 'duration_ms': round(ms, 2), 'face_count': len(faces), 'faces': faces})
    detector.close()
    return {'status': 'success', 'summary': summarize(results), 'results': results}


def run_insightface(previews: list[Path], max_side: int) -> dict[str, Any]:
    try:
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        app.prepare(ctx_id=-1, det_size=(640, 640))
    except Exception as exc:
        return {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
    results = []
    for p in previews:
        img = cv2.imread(str(p))
        if img is None:
            results.append({'preview': str(p), 'status': 'failed', 'error': 'cv2.imread failed'})
            continue
        h, w = img.shape[:2]
        scale = min(1.0, max_side / max(h, w))
        work = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
        t = time.perf_counter()
        faces_raw = app.get(work)
        ms = (time.perf_counter() - t) * 1000
        faces = []
        for f in faces_raw:
            x1, y1, x2, y2 = [float(v) / scale for v in f.bbox]
            bw, bh = x2 - x1, y2 - y1
            emb = getattr(f, 'embedding', None)
            faces.append({
                'box': {'x': round(x1, 1), 'y': round(y1, 1), 'w': round(bw, 1), 'h': round(bh, 1)},
                'score': round(float(getattr(f, 'det_score', 0.0)), 4),
                'area_ratio': round((bw * bh) / (w * h), 6),
                'landmarks_5': [[round(float(x) / scale, 1), round(float(y) / scale, 1)] for x, y in getattr(f, 'kps', [])] if getattr(f, 'kps', None) is not None else None,
                'embedding': {'shape': list(emb.shape), 'norm': round(float(np.linalg.norm(emb)), 4), 'sample_first_values': [round(float(v), 6) for v in emb[:8]]} if emb is not None else None,
            })
        results.append({'preview': str(p), 'status': 'success', 'width': w, 'height': h, 'duration_ms': round(ms, 2), 'face_count': len(faces), 'faces': faces})
    return {'status': 'success', 'summary': summarize(results), 'results': results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-dir', default=str(DEFAULT_CACHE))
    parser.add_argument('--limit', type=int, default=46)
    parser.add_argument('--max-side', type=int, default=1280)
    parser.add_argument('--models', nargs='*', default=['mediapipe', 'insightface'], choices=['mediapipe', 'insightface'])
    parser.add_argument('--output', default=str(DEFAULT_CACHE / 'face_model_benchmark.json'))
    args = parser.parse_args()
    cache = Path(args.cache_dir)
    previews = sorted((cache / 'previews').glob('*.jpg'))[:args.limit]
    payload = {'previews': len(previews), 'max_side': args.max_side, 'models': {}}
    if 'mediapipe' in args.models:
        print('benchmarking mediapipe...', flush=True)
        payload['models']['mediapipe'] = run_mediapipe(previews, args.max_side)
    if 'insightface' in args.models:
        print('benchmarking insightface...', flush=True)
        payload['models']['insightface'] = run_insightface(previews, args.max_side)
    out = Path(args.output)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v.get('summary', v) for k, v in payload['models'].items()}, ensure_ascii=False, indent=2))
    print('written:', out.resolve())
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
