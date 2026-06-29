#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


DEFAULT_APP = Path("src-tauri/target/release/bundle/macos/Cullary Runtime.app")
DEFAULT_DMG = Path("src-tauri/target/release/bundle/dmg/Cullary_0.1.0_aarch64.dmg")
DEFAULT_OUTPUT = Path("src-tauri/target/release/bundle/Cullary Runtime.release-summary.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def du_bytes(path: Path) -> int:
    proc = subprocess.run(["du", "-sk", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return int(proc.stdout.split()[0]) * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Cullary internal release artifact summary.")
    parser.add_argument("--app", default=str(DEFAULT_APP))
    parser.add_argument("--dmg", default=str(DEFAULT_DMG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--verification", default="passed")
    args = parser.parse_args()

    app = Path(args.app).expanduser().resolve()
    dmg = Path(args.dmg).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not app.is_dir():
        raise FileNotFoundError(app)
    if not dmg.is_file():
        raise FileNotFoundError(dmg)

    summary = {
        "schema_version": "1.0",
        "created_at_epoch": int(time.time()),
        "product": "Cullary Runtime",
        "version": "0.1.0",
        "target": "aarch64-apple-darwin",
        "channel": "internal-unsigned",
        "verification": args.verification,
        "artifacts": {
            "app": {
                "path": str(app),
                "size_bytes": du_bytes(app),
            },
            "dmg": {
                "path": str(dmg),
                "size_bytes": dmg.stat().st_size,
                "sha256": sha256_file(dmg),
            },
        },
        "notes": [
            "Unsigned and not notarized; intended for internal testing only.",
            "Runtime verification includes release app smoke and mounted DMG smoke.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
