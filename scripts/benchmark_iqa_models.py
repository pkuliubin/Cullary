#!/usr/bin/env python3
"""Benchmark pyiqa candidates on cached previews."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/cullary-mpl')
os.environ.setdefault('PYIQA_CACHE_DIR', str(Path('.cullary_cache/models/pyiqa').resolve()))

import pyiqa

DEFAULT_CACHE = Path('.cullary_cache')


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in results if r.get('status') == 'success']
    times = [r['duration_ms'] for r in ok]
    scores = [r['score'] for r in ok if isinstance(r.get('score'), (int, float))]
    return {
        'total': len(results),
        'success': len(ok),
        'failed': sum(1 for r in results if r.get('status') == 'failed'),
        'duration_ms': {
            'mean': round(statistics.mean(times), 2),
            'median': round(statistics.median(times), 2),
            'min': round(min(times), 2),
            'max': round(max(times), 2),
        } if times else None,
        'score': {
            'mean': round(statistics.mean(scores), 4),
            'min': round(min(scores), 4),
            'max': round(max(scores), 4),
        } if scores else None,
        'examples': ok[:5],
        'failures': [r for r in results if r.get('status') == 'failed'][:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-dir', default=str(DEFAULT_CACHE))
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--models', nargs='*', default=['brisque', 'niqe', 'piqe', 'nrqm'])
    parser.add_argument('--output', default=str(DEFAULT_CACHE / 'iqa_benchmark.json'))
    args = parser.parse_args()
    previews = sorted((Path(args.cache_dir) / 'previews').glob('*.jpg'))[:args.limit]
    payload = {'previews': [str(p) for p in previews], 'models': {}}
    for name in args.models:
        print(f'benchmarking {name}...', flush=True)
        try:
            metric = pyiqa.create_metric(name, device='cpu')
        except Exception as exc:
            payload['models'][name] = {'status': 'failed_to_create', 'error': f'{type(exc).__name__}: {exc}'}
            continue
        results = []
        for p in previews:
            try:
                start = time.perf_counter()
                score = metric(str(p))
                duration_ms = (time.perf_counter() - start) * 1000
                if hasattr(score, 'detach'):
                    score_value = float(score.detach().cpu().flatten()[0])
                else:
                    score_value = float(score)
                results.append({'preview': str(p), 'status': 'success', 'duration_ms': round(duration_ms, 2), 'score': round(score_value, 6)})
            except Exception as exc:
                results.append({'preview': str(p), 'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
        payload['models'][name] = {'status': 'success', 'summary': summarize(results), 'results': results}
    out = Path(args.output)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v.get('summary', v) for k, v in payload['models'].items()}, ensure_ascii=False, indent=2))
    print('written:', out.resolve())
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
