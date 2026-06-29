#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def app_resources(app: Path) -> Path:
    resources = app / "Contents" / "Resources"
    if not resources.is_dir():
        raise FileNotFoundError(f"App resources not found: {resources}")
    return resources


SUPPORTED_SAMPLE_EXTENSIONS = {".jpg", ".jpeg", ".3fr", ".heic"}


def prepare_sample_folder(source: Path, limit: int | None) -> Path:
    if not limit:
        return source
    sample = Path(tempfile.mkdtemp(prefix="cullary-app-full-smoke-"))
    copied = 0
    for path in sorted(source.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SAMPLE_EXTENSIONS:
            shutil.copy2(path, sample / path.name)
            copied += 1
            if copied >= limit:
                break
    if copied == 0:
        raise FileNotFoundError(f"No supported photos found for smoke sample: {source}")
    return sample


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Cullary.app bundled Python runtime resources.")
    parser.add_argument("--app", default="src-tauri/target/debug/bundle/macos/Cullary.app", help="Path to .app bundle")
    parser.add_argument("--folder", default="/Users/liubin/Desktop/TestImage", help="Photo folder with existing .cullary artifacts or source photos")
    parser.add_argument("--full", action="store_true", help="Run full pipeline instead of --skip-preprocess")
    parser.add_argument("--sample", action="store_true", help="Copy --limit photos from --folder into a temp folder before running full smoke")
    parser.add_argument("--force", action="store_true", help="Force re-run analyzers")
    parser.add_argument("--limit", type=int, help="Limit photos for a faster full pipeline smoke")
    parser.add_argument("--timeout", type=int, default=300, help="Subprocess timeout in seconds")
    args = parser.parse_args()

    app = Path(args.app).expanduser().resolve()
    source_folder = Path(args.folder).expanduser().resolve()
    folder = prepare_sample_folder(source_folder, args.limit) if args.full and args.sample else source_folder
    resources = app_resources(app)
    python = resources / "python" / "bin" / "python"
    config = resources / "config" / "preprocess.default.json"
    exiftool = resources / "bin" / "exiftool"
    models = resources / "models"
    python_src = resources / "python-src"

    required = [python, config, exiftool, models, python_src]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing runtime resources:\n" + "\n".join(missing))
    if not folder.is_dir():
        raise FileNotFoundError(f"Photo folder not found: {folder}")

    cache_root = Path(tempfile.mkdtemp(prefix="cullary-app-runtime-"))
    env = {
        "HOME": os.environ.get("HOME", str(Path.home())),
        "TMPDIR": os.environ.get("TMPDIR", tempfile.gettempdir()),
        "PYTHONPATH": str(python_src),
        "CULLARY_MODEL_DIR": str(models),
        "CULLARY_EXIFTOOL": str(exiftool),
        "MPLCONFIGDIR": str(cache_root / "matplotlib"),
        "XDG_CACHE_HOME": str(cache_root / "xdg"),
        "HF_HOME": str(cache_root / "huggingface"),
        "TRANSFORMERS_OFFLINE": "1",
        "PATH": f"{resources / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
    }

    cmd = [
        str(python),
        "-m",
        "cullary.pipeline",
        str(folder),
        "--config",
        str(config),
        "--progress",
        "jsonl",
    ]
    if not args.full:
        cmd.append("--skip-preprocess")
    if args.force:
        cmd.append("--force")
    if args.limit and not args.sample:
        cmd.extend(["--limit", str(args.limit)])

    proc = subprocess.run(cmd, cwd=str(resources), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=args.timeout)
    summary = {
        "app": str(app),
        "resources": str(resources),
        "folder": str(folder),
        "source_folder": str(source_folder),
        "sample": bool(args.full and args.sample),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout.splitlines()[-10:],
        "stderr_tail": proc.stderr.splitlines()[-20:],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
