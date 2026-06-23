#!/usr/bin/env python3
"""Cullary preprocessing CLI.

Creates a local JSONL + cache based analysis package for photo culling.
The source photos are read-only; all generated files live under the cache dir.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".heif", ".3fr"}
IGNORED_NAMES = {".DS_Store"}
DEFAULT_INPUT = Path("/Users/liubin/Desktop/TestImage")
DEFAULT_CACHE = Path(".cullary_cache")
PREVIEW_LONG_EDGE = 1600

ANALYZER_VERSIONS = {
    "metadata": "exiftool-json-v1",
    "preview": "preview-fallback-v1",
    "hash": "optional-pillow-numpy-hash-v1",
    "quality": "optional-pillow-numpy-v1",
    "embedding": "optional-light-model-probe-v1",
    "face": "optional-mediapipe-probe-v1",
    "iqa": "optional-lightweight-iqa-v1",
}


@dataclass
class AnalyzerResult:
    status: str
    version: str
    duration_ms: int
    error_message: str | None = None
    output_path: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "version": self.version,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }
        if self.output_path is not None:
            payload["output_path"] = self.output_path
        if self.data is not None:
            payload["data"] = self.data
        return payload


def timed(version: str, fn: Callable[[], tuple[str, dict[str, Any] | None, str | None, str | None]]) -> AnalyzerResult:
    start = time.perf_counter()
    try:
        status, data, error, output_path = fn()
    except Exception as exc:  # Keep analyzer failures isolated.
        status, data, error, output_path = "failed", None, f"{type(exc).__name__}: {exc}", None
    return AnalyzerResult(
        status=status,
        version=version,
        duration_ms=int((time.perf_counter() - start) * 1000),
        error_message=error,
        output_path=output_path,
        data=data,
    )


def run_cmd(args: list[str], *, stdout_path: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    if stdout_path is None:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    with stdout_path.open("wb") as out:
        return subprocess.run(args, stdout=out, stderr=subprocess.PIPE, timeout=timeout, check=False)


def ensure_tools() -> dict[str, str | None]:
    return {"exiftool": shutil.which("exiftool"), "sips": shutil.which("sips")}


def photo_id_for(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:20]


def scan_files(input_dir: Path) -> tuple[list[Path], dict[str, int]]:
    files: list[Path] = []
    ignored: dict[str, int] = {}
    for root, _, names in os.walk(input_dir):
        for name in names:
            path = Path(root) / name
            suffix = path.suffix.lower()
            if name in IGNORED_NAMES or suffix == ".crdownload":
                ignored[suffix or name] = ignored.get(suffix or name, 0) + 1
                continue
            if suffix in SUPPORTED_EXTENSIONS:
                files.append(path)
            else:
                ignored[suffix or "<none>"] = ignored.get(suffix or "<none>", 0) + 1
    return sorted(files), ignored


def read_existing_manifest(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records[record["source_id"]] = record
            except Exception:
                continue
    return records


def is_unchanged(record: dict[str, Any] | None, stat: os.stat_result) -> bool:
    if not record:
        return False
    source = record.get("source", {})
    return source.get("size") == stat.st_size and source.get("mtime_ns") == stat.st_mtime_ns


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def exiftool_json(path: Path, grouped: bool = False) -> dict[str, Any]:
    args = ["exiftool", "-json", "-n"]
    if grouped:
        args.extend(["-G1", "-a", "-s"])
    args.append(str(path))
    proc = run_cmd(args, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    data = json.loads(proc.stdout.decode("utf-8"))
    if not data:
        raise RuntimeError("exiftool returned no JSON")
    return data[0]


def extract_metadata(source: Path, output_path: Path) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        metadata = exiftool_json(source, grouped=False)
        useful = {
            "file_name": metadata.get("FileName"),
            "file_type": metadata.get("FileType"),
            "mime_type": metadata.get("MIMEType"),
            "image_width": metadata.get("ImageWidth"),
            "image_height": metadata.get("ImageHeight"),
            "date_time_original": metadata.get("DateTimeOriginal"),
            "create_date": metadata.get("CreateDate"),
            "make": metadata.get("Make"),
            "model": metadata.get("Model"),
            "lens_model": metadata.get("LensModel"),
            "focal_length": metadata.get("FocalLength"),
            "exposure_time": metadata.get("ExposureTime"),
            "f_number": metadata.get("FNumber"),
            "iso": metadata.get("ISO"),
            "orientation": metadata.get("Orientation"),
        }
        payload = {"useful": useful, "raw": metadata}
        write_json(output_path, payload)
        return "success", {"useful": useful}, None, str(output_path)

    return timed(ANALYZER_VERSIONS["metadata"], work)


def is_jpeg(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"\xff\xd8"
    except OSError:
        return False


def is_jpeg_bytes(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8")


def extract_with_exiftool_binary(source: Path, tag: str, dest: Path) -> bool:
    proc = run_cmd(["exiftool", "-b", f"-{tag}", str(source)], stdout_path=dest, timeout=120)
    if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0 and is_jpeg(dest):
        return True
    dest.unlink(missing_ok=True)
    return False


def get_grouped_tag(metadata: dict[str, Any], group: str, name: str) -> Any:
    return metadata.get(f"{group}:{name}")


def extract_3fr_ifd0_preview(source: Path, dest: Path) -> tuple[bool, dict[str, Any]]:
    grouped = exiftool_json(source, grouped=True)
    offset = get_grouped_tag(grouped, "IFD0", "StripOffsets")
    count = get_grouped_tag(grouped, "IFD0", "StripByteCounts")
    compression = get_grouped_tag(grouped, "IFD0", "Compression")
    subfile_type = get_grouped_tag(grouped, "IFD0", "SubfileType")
    info = {
        "ifd0_strip_offset": offset,
        "ifd0_strip_byte_count": count,
        "ifd0_compression": compression,
        "ifd0_subfile_type": subfile_type,
    }
    if offset is None or count is None:
        return False, info
    try:
        offset_int = int(offset)
        count_int = int(count)
    except (TypeError, ValueError):
        return False, info
    if offset_int < 0 or count_int <= 0:
        return False, info
    with source.open("rb") as handle:
        handle.seek(offset_int)
        data = handle.read(count_int)
    if not is_jpeg_bytes(data):
        info["jpeg_header_valid"] = False
        return False, info
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    info["jpeg_header_valid"] = True
    return True, info


def extract_preview(source: Path, dest: Path) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        suffix = source.suffix.lower()
        dest.parent.mkdir(parents=True, exist_ok=True)
        attempts: list[dict[str, Any]] = []

        if suffix in {".jpg", ".jpeg"}:
            shutil.copy2(source, dest)
            return "success", {"method": "copy_source_jpeg", "attempts": attempts}, None, str(dest)

        for tag in ("PreviewImage", "JpgFromRaw", "ThumbnailImage"):
            ok = extract_with_exiftool_binary(source, tag, dest)
            attempts.append({"method": f"exiftool:{tag}", "success": ok})
            if ok:
                return "success", {"method": f"exiftool:{tag}", "attempts": attempts}, None, str(dest)

        if suffix == ".3fr":
            ok, info = extract_3fr_ifd0_preview(source, dest)
            attempts.append({"method": "3fr_ifd0_byte_slice", "success": ok, "info": info})
            if ok:
                return "success", {"method": "3fr_ifd0_byte_slice", "attempts": attempts}, None, str(dest)

        if suffix in {".heic", ".heif", ".jpg", ".jpeg"} and shutil.which("sips"):
            proc = run_cmd(["sips", "-s", "format", "jpeg", "-Z", str(PREVIEW_LONG_EDGE), str(source), "--out", str(dest)], timeout=120)
            ok = proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0 and is_jpeg(dest)
            attempts.append({"method": "sips_jpeg_thumbnail", "success": ok})
            if ok:
                return "success", {"method": "sips_jpeg_thumbnail", "attempts": attempts}, None, str(dest)
            dest.unlink(missing_ok=True)

        return "failed", {"attempts": attempts}, "no preview extraction method succeeded", None

    return timed(ANALYZER_VERSIONS["preview"], work)


def optional_import(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def analyze_hash(preview_path: Path, output_path: Path) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        pil = optional_import("PIL.Image")
        np = optional_import("numpy")
        if pil is None or np is None:
            return "skipped", {"required": ["Pillow", "numpy"]}, "optional dependencies not installed", None
        image = pil.open(preview_path).convert("L")  # type: ignore[attr-defined]
        small = image.resize((8, 8))
        arr = np.asarray(small, dtype=np.float32)
        ahash_bits = arr > arr.mean()

        dhash_img = image.resize((9, 8))
        dhash_arr = np.asarray(dhash_img, dtype=np.float32)
        dhash_bits = dhash_arr[:, 1:] > dhash_arr[:, :-1]

        def bits_to_hex(bits: Any) -> str:
            flat = [1 if bool(v) else 0 for v in bits.ravel()]
            value = 0
            for bit in flat:
                value = (value << 1) | bit
            return f"{value:0{len(flat) // 4}x}"

        data = {"ahash": bits_to_hex(ahash_bits), "dhash": bits_to_hex(dhash_bits)}
        write_json(output_path, data)
        return "success", data, None, str(output_path)

    return timed(ANALYZER_VERSIONS["hash"], work)


def analyze_quality(preview_path: Path, output_path: Path) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        pil = optional_import("PIL.Image")
        np = optional_import("numpy")
        if pil is None or np is None:
            return "skipped", {"required": ["Pillow", "numpy"]}, "optional dependencies not installed", None
        image = pil.open(preview_path).convert("L")  # type: ignore[attr-defined]
        image.thumbnail((512, 512))
        arr = np.asarray(image, dtype=np.float32)
        gy, gx = np.gradient(arr)
        tenengrad = float(np.mean(gx * gx + gy * gy))
        hist = np.bincount(arr.astype(np.uint8).ravel(), minlength=256)
        total = int(hist.sum()) or 1
        shadows = float(hist[:5].sum() / total)
        highlights = float(hist[251:].sum() / total)
        contrast = float(arr.std() / 255.0)
        data = {
            "sharpness_tenengrad": tenengrad,
            "shadow_clip_ratio": shadows,
            "highlight_clip_ratio": highlights,
            "contrast_std_ratio": contrast,
        }
        write_json(output_path, data)
        return "success", data, None, str(output_path)

    return timed(ANALYZER_VERSIONS["quality"], work)


def analyze_embedding(preview_path: Path, output_path: Path) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        missing = [name for name in ("torch", "transformers") if optional_import(name) is None]
        if missing:
            return "skipped", {"preferred_models": ["MobileCLIP", "CLIP ViT-B/32", "DINOv2-small"], "missing": missing}, "optional model dependencies not installed", None
        return "skipped", {"reason": "model backend intentionally not selected in first CLI scaffold"}, "model benchmark not configured", None

    return timed(ANALYZER_VERSIONS["embedding"], work)


def analyze_face(preview_path: Path, output_path: Path) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        if optional_import("mediapipe") is None:
            return "skipped", {"preferred_models": ["MediaPipe", "YuNet"]}, "optional face dependency not installed", None
        return "skipped", {"reason": "face backend present but not wired in this no-dependency scaffold"}, "face analyzer not configured", None

    return timed(ANALYZER_VERSIONS["face"], work)


def analyze_iqa(preview_path: Path, output_path: Path, quality_result: AnalyzerResult) -> AnalyzerResult:
    def work() -> tuple[str, dict[str, Any] | None, str | None, str | None]:
        if quality_result.status != "success" or not quality_result.data:
            return "skipped", {"depends_on": "quality"}, "quality metrics unavailable", None
        q = quality_result.data
        sharp = min(float(q.get("sharpness_tenengrad", 0.0)) / 2000.0, 1.0)
        exposure_penalty = min(float(q.get("shadow_clip_ratio", 0.0)) + float(q.get("highlight_clip_ratio", 0.0)), 1.0)
        contrast = min(float(q.get("contrast_std_ratio", 0.0)) / 0.25, 1.0)
        score = max(0.0, min(1.0, 0.45 * sharp + 0.35 * contrast + 0.20 * (1.0 - exposure_penalty)))
        data = {"lightweight_iqa_score": score, "method": "quality_metric_proxy"}
        write_json(output_path, data)
        return "success", data, None, str(output_path)

    return timed(ANALYZER_VERSIONS["iqa"], work)


def source_record(source: Path, source_id: str, stat: os.stat_result) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source": {
            "path": str(source),
            "extension": source.suffix.lower(),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        },
    }


def process_photo(source: Path, cache_dir: Path, existing: dict[str, Any] | None, force: bool) -> dict[str, Any]:
    stat = source.stat()
    source_id = photo_id_for(source)
    record = source_record(source, source_id, stat)
    analysis_dir = cache_dir / "analysis" / source_id
    preview_path = cache_dir / "previews" / f"{source_id}.jpg"
    analysis_path = analysis_dir / "analysis.json"

    if not force and is_unchanged(existing, stat) and analysis_path.exists():
        reused = dict(existing or record)
        reused["run_status"] = "skipped_unchanged"
        return reused

    metadata_result = extract_metadata(source, analysis_dir / "metadata.json")
    preview_result = extract_preview(source, preview_path)

    if preview_result.status == "success" and preview_path.exists():
        hash_result = analyze_hash(preview_path, analysis_dir / "hash.json")
        quality_result = analyze_quality(preview_path, analysis_dir / "quality.json")
        embedding_result = analyze_embedding(preview_path, analysis_dir / "embedding.json")
        face_result = analyze_face(preview_path, analysis_dir / "faces.json")
        iqa_result = analyze_iqa(preview_path, analysis_dir / "iqa.json", quality_result)
    else:
        skipped = lambda name, reason: AnalyzerResult("skipped", ANALYZER_VERSIONS[name], 0, reason, None, None)
        hash_result = skipped("hash", "preview unavailable")
        quality_result = skipped("quality", "preview unavailable")
        embedding_result = skipped("embedding", "preview unavailable")
        face_result = skipped("face", "preview unavailable")
        iqa_result = skipped("iqa", "preview unavailable")

    analyzers = {
        "metadata": metadata_result.to_dict(),
        "preview": preview_result.to_dict(),
        "hash": hash_result.to_dict(),
        "quality": quality_result.to_dict(),
        "embedding": embedding_result.to_dict(),
        "face": face_result.to_dict(),
        "iqa": iqa_result.to_dict(),
    }
    record.update({"preview_path": str(preview_path) if preview_path.exists() else None, "analysis_path": str(analysis_path), "analyzers": analyzers, "run_status": "processed"})
    write_json(analysis_path, record)
    return record


def summarize(records: list[dict[str, Any]], ignored: dict[str, int], started_at: float, tools: dict[str, str | None]) -> dict[str, Any]:
    analyzer_counts: dict[str, dict[str, int]] = {}
    run_status_counts: dict[str, int] = {}
    failures: list[dict[str, Any]] = []
    for record in records:
        run_status = record.get("run_status", "unknown")
        run_status_counts[run_status] = run_status_counts.get(run_status, 0) + 1
        for name, result in record.get("analyzers", {}).items():
            status = result.get("status", "unknown")
            analyzer_counts.setdefault(name, {})[status] = analyzer_counts.setdefault(name, {}).get(status, 0) + 1
            if status == "failed":
                failures.append({"source": record.get("source", {}).get("path"), "analyzer": name, "error": result.get("error_message")})
    by_extension: dict[str, int] = {}
    for record in records:
        ext = record.get("source", {}).get("extension", "")
        by_extension[ext] = by_extension.get(ext, 0) + 1
    return {
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
        "tools": tools,
        "total_photos": len(records),
        "by_extension": by_extension,
        "ignored": ignored,
        "run_status_counts": run_status_counts,
        "analyzer_counts": analyzer_counts,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cullary local preprocessing CLI")
    parser.add_argument("folder", nargs="?", default=str(DEFAULT_INPUT), help="Folder to scan")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE), help="Cache output directory")
    parser.add_argument("--force", action="store_true", help="Re-run analyzers even when file stat is unchanged")
    args = parser.parse_args(argv)

    input_dir = Path(args.folder).expanduser().resolve()
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input folder does not exist or is not a directory: {input_dir}", file=sys.stderr)
        return 2

    tools = ensure_tools()
    if not tools["exiftool"]:
        print("exiftool is required but was not found on PATH", file=sys.stderr)
        return 2

    started_at = time.perf_counter()
    files, ignored = scan_files(input_dir)
    manifest_path = cache_dir / "manifest.jsonl"
    existing = read_existing_manifest(manifest_path)
    records: list[dict[str, Any]] = []

    for index, source in enumerate(files, start=1):
        source_id = photo_id_for(source)
        print(f"[{index}/{len(files)}] {source.name}", flush=True)
        record = process_photo(source, cache_dir, existing.get(source_id), args.force)
        records.append(record)

    append_jsonl(manifest_path, records)
    summary = summarize(records, ignored, started_at, tools)
    write_json(cache_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Manifest: {manifest_path}")
    print(f"Summary:  {cache_dir / 'run_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
