#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import stat
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Avoid copying macOS quarantine/provenance xattrs into the app bundle resources.
    shutil.copyfile(src, dst)
    dst.chmod(src.stat().st_mode & 0o777 | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IWUSR)


def copy_tree(src: Path, dst: Path, *, symlinks: bool = False, ignore=None) -> None:
    if not src.is_dir():
        raise FileNotFoundError(src)
    if dst.exists():
        shutil.rmtree(dst)
    ignore = ignore or shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store")
    shutil.copytree(src, dst, symlinks=symlinks, ignore=ignore)


def copy_python_runtime(src: Path, dst: Path) -> None:
    if not (src / "bin" / "python").is_file():
        raise FileNotFoundError(f"python runtime does not contain bin/python: {src}")
    copy_tree(
        src,
        dst,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".DS_Store",
            "man",
            "include",
            "conda-meta",
            "share",
        ),
    )
    python = dst / "bin" / "python"
    python.chmod(python.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_tree_owner_writable(root: Path) -> int:
    changed = 0
    if not root.exists():
        return changed
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        try:
            mode = path.stat().st_mode
            if not mode & stat.S_IWUSR:
                path.chmod(mode | stat.S_IWUSR)
                changed += 1
        except OSError:
            continue
    return changed


def remove_broken_symlinks(root: Path) -> list[str]:
    removed: list[str] = []
    if not root.exists():
        return removed
    for path in sorted(root.rglob("*")):
        if path.is_symlink() and not path.exists():
            removed.append(str(path.relative_to(root)))
            path.unlink()
    return removed


def stage_models(manifest_path: Path, output_dir: Path) -> list[str]:
    manifest = load_json(manifest_path)
    source_root = expand(manifest["root"])
    staged: list[str] = []
    missing: list[str] = []
    for rel in manifest.get("required_paths", []):
        src = source_root / rel
        dst = output_dir / "models" / rel
        if not src.is_file():
            missing.append(rel)
            continue
        copy_file(src, dst)
        staged.append(rel)
    if missing:
        raise RuntimeError("missing required model files:\n" + "\n".join(f"- {item}" for item in missing))
    return staged


def find_exiftool(explicit: str | None) -> Path:
    if explicit:
        path = expand(explicit)
        if path.is_file():
            return path
        raise FileNotFoundError(path)
    found = shutil.which("exiftool")
    if found:
        return Path(found).resolve()
    for candidate in (Path("/usr/local/bin/exiftool"), Path("/opt/homebrew/bin/exiftool")):
        if candidate.is_file():
            return candidate
    raise RuntimeError("exiftool not found; pass --exiftool /path/to/exiftool")


def write_runtime_json(output_dir: Path, python_binary: str) -> None:
    runtime = {
        "schema_version": "1.0",
        "pipeline_mode": "python_module",
        "python_binary": python_binary,
        "pythonpath": "resources/python-src",
        "working_dir": "resources",
        "module": "cullary.pipeline",
        "config_path": "resources/config/preprocess.default.json",
        "model_dir": "resources/models",
        "exiftool_binary": "resources/bin/exiftool",
    }
    (output_dir / "runtime.json").write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage Cullary runtime resources for Tauri packaging.")
    parser.add_argument("--output", default=str(REPO_ROOT / "build/cullary-runtime"), help="Output staging directory")
    parser.add_argument("--models-manifest", default=str(REPO_ROOT / "packaging/models.manifest.json"))
    parser.add_argument("--exiftool", help="Explicit exiftool binary")
    parser.add_argument("--python-env", help="Copy an existing Python environment into output/python for local smoke testing")
    parser.add_argument("--python-binary", default="/opt/anaconda3/envs/hippo/bin/python", help="Python binary to use when not staging a runtime")
    args = parser.parse_args()

    output = expand(args.output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copy_tree(REPO_ROOT / "src" / "cullary", output / "python-src" / "cullary")
    copy_file(REPO_ROOT / "config" / "preprocess.default.json", output / "config" / "preprocess.default.json")
    staged_models = stage_models(expand(args.models_manifest), output)
    copy_file(find_exiftool(args.exiftool), output / "bin" / "exiftool")
    removed_broken_symlinks: list[str] = []
    made_writable = 0
    if args.python_env:
        copy_python_runtime(expand(args.python_env), output / "python")
        removed_broken_symlinks = remove_broken_symlinks(output / "python")
        made_writable += make_tree_owner_writable(output / "python")
        python_binary = "resources/python/bin/python"
    else:
        python_binary = args.python_binary
    made_writable += make_tree_owner_writable(output / "bin")
    write_runtime_json(output, python_binary)

    summary = {
        "output": str(output),
        "python_src": "python-src/cullary",
        "config": "config/preprocess.default.json",
        "models": len(staged_models),
        "exiftool": "bin/exiftool",
        "runtime": "runtime.json",
        "python_runtime": "python" if args.python_env else None,
        "python_binary": python_binary,
        "removed_broken_symlinks": removed_broken_symlinks,
        "made_owner_writable": made_writable,
    }
    (output / "package_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
