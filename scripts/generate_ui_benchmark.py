#!/usr/bin/env python3
"""Generate a static image-grid benchmark page for Cullary UI experiments."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def discover_images(path: Path) -> list[Path]:
    if path.is_file() and path.name.endswith(".jsonl"):
        images: list[Path] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                preview = record.get("preview_path")
                if preview and Path(preview).exists():
                    images.append(Path(preview).resolve())
        return images
    if path.is_dir():
        return sorted(p.resolve() for p in path.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    return []


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def build_thumbnails(images: list[Path], thumb_dir: Path, edge: int) -> list[Path]:
    thumb_dir.mkdir(parents=True, exist_ok=True)
    sips = shutil.which("sips")
    thumbs: list[Path] = []
    for index, source in enumerate(images):
        dest = thumb_dir / f"{index:06d}_{source.stem}.jpg"
        if not dest.exists() or dest.stat().st_size == 0:
            if sips:
                subprocess.run(
                    [sips, "-s", "format", "jpeg", "-Z", str(edge), str(source), "--out", str(dest)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            if not dest.exists() or dest.stat().st_size == 0:
                shutil.copy2(source, dest)
        thumbs.append(dest.resolve())
    return thumbs


def build_html(images: list[Path], repeat: int, output: Path) -> str:
    urls = [file_url(path) for path in images]
    dataset = (urls * repeat)[: len(urls) * repeat]
    data_json = json.dumps(dataset)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Cullary UI Image Benchmark</title>
  <style>
    :root {{
      --bg: #10110f;
      --panel: #191b17;
      --text: #f4f0e6;
      --muted: #aaa491;
      --accent: #d6ff72;
      --line: #303428;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    header {{ position: sticky; top: 0; z-index: 10; display: flex; gap: 12px; align-items: center; padding: 12px 16px; background: rgba(16,17,15,.94); border-bottom: 1px solid var(--line); }}
    button {{ border: 1px solid var(--line); background: var(--panel); color: var(--text); padding: 8px 10px; border-radius: 8px; cursor: pointer; }}
    button.active {{ border-color: var(--accent); color: var(--accent); }}
    .metric {{ color: var(--muted); }}
    .metric b {{ color: var(--text); font-weight: 600; }}
    #grid {{ padding: 16px; }}
    .full-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }}
    .tile {{ background: #22261d; border: 1px solid #2d3327; border-radius: 10px; overflow: hidden; aspect-ratio: 1 / 1; }}
    .tile img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .virtual-viewport {{ height: calc(100vh - 58px); overflow: auto; padding: 16px; }}
    .virtual-spacer {{ position: relative; }}
    .virtual-row {{ position: absolute; left: 0; right: 0; display: grid; grid-template-columns: repeat(var(--cols), 1fr); gap: 10px; }}
  </style>
</head>
<body>
  <header>
    <button id=\"fullBtn\">Full render</button>
    <button id=\"virtualBtn\" class=\"active\">Virtual render</button>
    <span class=\"metric\">images: <b id=\"count\"></b></span>
    <span class=\"metric\">mounted: <b id=\"mounted\"></b></span>
    <span class=\"metric\">render ms: <b id=\"renderMs\"></b></span>
    <span class=\"metric\">decoded: <b id=\"decoded\"></b></span>
    <span class=\"metric\">decode p95 ms: <b id=\"decodeP95\"></b></span>
  </header>
  <main id=\"app\"></main>
  <script>
    const images = {data_json};
    const app = document.getElementById('app');
    const fullBtn = document.getElementById('fullBtn');
    const virtualBtn = document.getElementById('virtualBtn');
    const metrics = {{
      count: document.getElementById('count'),
      mounted: document.getElementById('mounted'),
      renderMs: document.getElementById('renderMs'),
      decoded: document.getElementById('decoded'),
      decodeP95: document.getElementById('decodeP95'),
    }};
    const decodeTimes = [];
    metrics.count.textContent = images.length;

    function percentile(values, p) {{
      if (!values.length) return 0;
      const sorted = [...values].sort((a, b) => a - b);
      const idx = Math.min(sorted.length - 1, Math.round((p / 100) * (sorted.length - 1)));
      return sorted[idx];
    }}

    function resetMetrics(start) {{
      decodeTimes.length = 0;
      metrics.mounted.textContent = '0';
      metrics.renderMs.textContent = String(Math.round(performance.now() - start));
      metrics.decoded.textContent = '0';
      metrics.decodeP95.textContent = '0';
    }}

    function makeTile(src, index) {{
      const tile = document.createElement('div');
      tile.className = 'tile';
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = 'preview ' + index;
      const t = performance.now();
      img.onload = () => {{
        decodeTimes.push(performance.now() - t);
        metrics.decoded.textContent = String(decodeTimes.length);
        metrics.decodeP95.textContent = String(Math.round(percentile(decodeTimes, 95)));
      }};
      img.src = src;
      tile.appendChild(img);
      return tile;
    }}

    function renderFull() {{
      const start = performance.now();
      app.innerHTML = '<div id=\"grid\" class=\"full-grid\"></div>';
      const grid = document.getElementById('grid');
      const frag = document.createDocumentFragment();
      images.forEach((src, index) => frag.appendChild(makeTile(src, index)));
      grid.appendChild(frag);
      resetMetrics(start);
      metrics.mounted.textContent = String(images.length);
      fullBtn.classList.add('active');
      virtualBtn.classList.remove('active');
    }}

    function renderVirtual() {{
      const start = performance.now();
      app.innerHTML = '<div class=\"virtual-viewport\"><div class=\"virtual-spacer\"></div></div>';
      const viewport = app.querySelector('.virtual-viewport');
      const spacer = app.querySelector('.virtual-spacer');
      const gap = 10;
      const minTile = 150;
      const overscan = 4;
      let cols = 1;
      let rowHeight = 160;

      function layout() {{
        cols = Math.max(1, Math.floor((viewport.clientWidth + gap) / (minTile + gap)));
        const tileWidth = Math.floor((viewport.clientWidth - gap * (cols - 1)) / cols);
        rowHeight = tileWidth + gap;
        spacer.style.height = Math.ceil(images.length / cols) * rowHeight + 'px';
        spacer.style.setProperty('--cols', cols);
        draw();
      }}

      function draw() {{
        const firstRow = Math.max(0, Math.floor(viewport.scrollTop / rowHeight) - overscan);
        const visibleRows = Math.ceil(viewport.clientHeight / rowHeight) + overscan * 2;
        const lastRow = Math.min(Math.ceil(images.length / cols), firstRow + visibleRows);
        const frag = document.createDocumentFragment();
        let mounted = 0;
        for (let row = firstRow; row < lastRow; row++) {{
          const rowEl = document.createElement('div');
          rowEl.className = 'virtual-row';
          rowEl.style.top = row * rowHeight + 'px';
          rowEl.style.height = (rowHeight - gap) + 'px';
          for (let col = 0; col < cols; col++) {{
            const index = row * cols + col;
            if (index >= images.length) break;
            rowEl.appendChild(makeTile(images[index], index));
            mounted++;
          }}
          frag.appendChild(rowEl);
        }}
        spacer.replaceChildren(frag);
        metrics.mounted.textContent = String(mounted);
      }}

      viewport.addEventListener('scroll', () => requestAnimationFrame(draw), {{ passive: true }});
      window.addEventListener('resize', layout);
      resetMetrics(start);
      layout();
      metrics.renderMs.textContent = String(Math.round(performance.now() - start));
      virtualBtn.classList.add('active');
      fullBtn.classList.remove('active');
    }}

    fullBtn.onclick = renderFull;
    virtualBtn.onclick = renderVirtual;
    renderVirtual();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Cullary static UI image benchmark")
    parser.add_argument("path", help="Preview directory or manifest.jsonl")
    parser.add_argument("--repeat", type=int, default=25, help="Repeat discovered images to simulate larger folders")
    parser.add_argument("--output", default="docs/ui-image-benchmark.html")
    parser.add_argument("--thumb-dir", default=None, help="Generate/use thumbnails in this directory")
    parser.add_argument("--thumb-edge", type=int, default=360, help="Thumbnail long edge when --thumb-dir is set")
    args = parser.parse_args()

    images = discover_images(Path(args.path).expanduser())
    if not images:
        print(f"No images found under: {args.path}")
        return 2

    if args.thumb_dir:
        images = build_thumbnails(images, Path(args.thumb_dir).expanduser().resolve(), args.thumb_edge)

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(images, args.repeat, output), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Source images: {len(images)}")
    print(f"Benchmark images: {len(images) * args.repeat}")
    print(f"Open: {output.as_uri()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
