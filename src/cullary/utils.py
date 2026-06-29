from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def short_hash(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def config_hash(config: dict[str, Any], stage: str) -> str:
    relevant = config.get(stage, {}) if isinstance(config.get(stage, {}), dict) else {}
    return short_hash(stable_json(relevant))


def source_id_for(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:20]


def sanitize_display_id(path: Path) -> str:
    stem = path.stem.strip() or "photo"
    ext = path.suffix.lower().lstrip(".") or "file"
    raw = f"{stem}_{ext.upper()}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    return safe or f"photo_{short_hash(path.name, 8)}"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(stable_json(record) + "\n" for record in records))


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            records[str(record["source_id"])] = record
        except Exception:
            continue
    return records


def run_cmd(args: list[str], *, stdout_path: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[bytes]:
    if stdout_path is None:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as out:
        return subprocess.run(args, stdout=out, stderr=subprocess.PIPE, timeout=timeout, check=False)


def relative_to_folder(path: Path, folder: Path) -> str:
    try:
        return str(path.relative_to(folder))
    except ValueError:
        return str(path)


def cache_relative(path: Path, folder: Path) -> str:
    return relative_to_folder(path, folder)


def ensure_tools() -> dict[str, str | None]:
    exiftool = os.environ.get("CULLARY_EXIFTOOL")
    return {"exiftool": exiftool or shutil.which("exiftool"), "sips": shutil.which("sips")}


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.expanduser().read_text(encoding="utf-8"))
    model_dir = os.environ.get("CULLARY_MODEL_DIR") or config.get("models", {}).get("model_dir", "~/.cullary/models")
    config.setdefault("models", {})["model_dir"] = str(Path(model_dir).expanduser())
    return config
