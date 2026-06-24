from __future__ import annotations

from pathlib import Path
from typing import Any

from cullary.utils import run_cmd, write_json


def exiftool_json(path: Path, grouped: bool = False) -> dict[str, Any]:
    args = ["exiftool", "-json", "-n"]
    if grouped:
        args.extend(["-G1", "-a", "-s"])
    args.append(str(path))
    proc = run_cmd(args, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip())
    data = __import__("json").loads(proc.stdout.decode("utf-8"))
    if not data:
        raise RuntimeError("exiftool returned no JSON")
    return data[0]


def is_jpeg(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"\xff\xd8"
    except OSError:
        return False


def extract_with_exiftool_binary(source: Path, tag: str, dest: Path) -> bool:
    proc = run_cmd(["exiftool", "-b", f"-{tag}", str(source)], stdout_path=dest, timeout=180)
    if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0 and is_jpeg(dest):
        return True
    dest.unlink(missing_ok=True)
    return False


def extract_3fr_ifd0_preview(source: Path, dest: Path) -> tuple[bool, dict[str, Any]]:
    grouped = exiftool_json(source, grouped=True)
    offset = grouped.get("IFD0:StripOffsets")
    count = grouped.get("IFD0:StripByteCounts")
    info = {"ifd0_strip_offset": offset, "ifd0_strip_byte_count": count, "ifd0_compression": grouped.get("IFD0:Compression")}
    try:
        offset_int = int(offset)
        count_int = int(count)
    except Exception:
        return False, info
    if offset_int < 0 or count_int <= 0:
        return False, info
    with source.open("rb") as handle:
        handle.seek(offset_int)
        data = handle.read(count_int)
    if not data.startswith(b"\xff\xd8"):
        info["jpeg_header_valid"] = False
        return False, info
    dest.write_bytes(data)
    info["jpeg_header_valid"] = True
    return True, info


def image_dimensions(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as img:
        return img.width, img.height


def make_resized_jpeg(source: Path, dest: Path, long_edge: int) -> None:
    from PIL import Image, ImageOps

    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
        img.save(dest, "JPEG", quality=90, optimize=True)


def resize_jpeg_in_place(path: Path, long_edge: int) -> None:
    make_resized_jpeg(path, path, long_edge)


def extract_metadata(source: Path, raw_output_path: Path) -> dict[str, Any]:
    metadata = exiftool_json(source)
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
    write_json(raw_output_path, metadata)
    return {"useful": useful, "raw_path": None}


def extract_preview(source: Path, dest: Path, long_edge: int, sips_path: str | None) -> tuple[dict[str, Any] | None, str | None]:
    attempts: list[dict[str, Any]] = []
    dest.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        make_resized_jpeg(source, dest, long_edge)
        width, height = image_dimensions(dest)
        return {"preview_path": None, "preview_width": width, "preview_height": height, "preview_method": "source_jpeg_resize"}, None

    for tag in ("PreviewImage", "JpgFromRaw", "ThumbnailImage"):
        ok = extract_with_exiftool_binary(source, tag, dest)
        attempts.append({"method": f"exiftool:{tag}", "success": ok})
        if ok:
            resize_jpeg_in_place(dest, long_edge)
            width, height = image_dimensions(dest)
            return {"preview_path": None, "preview_width": width, "preview_height": height, "preview_method": f"exiftool:{tag}", "preview_attempts": attempts}, None

    if suffix == ".3fr":
        ok, info = extract_3fr_ifd0_preview(source, dest)
        attempts.append({"method": "3fr_ifd0_byte_slice", "success": ok, "info": info})
        if ok:
            resize_jpeg_in_place(dest, long_edge)
            width, height = image_dimensions(dest)
            return {"preview_path": None, "preview_width": width, "preview_height": height, "preview_method": "3fr_ifd0_byte_slice", "preview_attempts": attempts}, None

    if suffix in {".heic", ".heif", ".jpg", ".jpeg"} and sips_path:
        proc = run_cmd(["sips", "-s", "format", "jpeg", "-Z", str(long_edge), str(source), "--out", str(dest)], timeout=180)
        ok = proc.returncode == 0 and is_jpeg(dest)
        attempts.append({"method": "sips_jpeg", "success": ok})
        if ok:
            width, height = image_dimensions(dest)
            return {"preview_path": None, "preview_width": width, "preview_height": height, "preview_method": "sips_jpeg", "preview_attempts": attempts}, None
    dest.unlink(missing_ok=True)
    return {"preview_attempts": attempts}, "no preview extraction method succeeded"


def create_thumb(preview_path: Path, thumb_path: Path, long_edge: int) -> dict[str, Any]:
    make_resized_jpeg(preview_path, thumb_path, long_edge)
    width, height = image_dimensions(thumb_path)
    return {"thumb_path": None, "thumb_width": width, "thumb_height": height}
