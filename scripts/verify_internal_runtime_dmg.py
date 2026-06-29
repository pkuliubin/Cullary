#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path


DEFAULT_DMG = Path("src-tauri/target/release/bundle/dmg/Cullary_0.1.0_aarch64.dmg")
DEFAULT_APP_NAME = "Cullary Runtime.app"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def attach_dmg(dmg: Path) -> tuple[str, str]:
    proc = run(["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(dmg)], check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace") or proc.stdout.decode("utf-8", "replace"))
    payload = plistlib.loads(proc.stdout)
    mount_point = None
    device = None
    for entity in payload.get("system-entities", []):
        if entity.get("mount-point"):
            mount_point = entity["mount-point"]
            device = entity.get("dev-entry") or device
            break
        if entity.get("dev-entry"):
            device = entity.get("dev-entry")
    if not mount_point or not device:
        raise RuntimeError("failed to find mounted DMG volume in hdiutil output")
    return device, mount_point


def detach(device: str) -> None:
    subprocess.run(["hdiutil", "detach", device], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mount and smoke test the internal Cullary Runtime DMG.")
    parser.add_argument("--dmg", default=str(DEFAULT_DMG))
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--folder", default="/Users/liubin/Desktop/TestImage")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    dmg = Path(args.dmg).expanduser().resolve()
    if not dmg.is_file():
        raise FileNotFoundError(dmg)

    device = None
    mount_point = None
    try:
        device, mount_point = attach_dmg(dmg)
        mount = Path(mount_point)
        entries = sorted(path.name for path in mount.iterdir() if path.name != ".fseventsd")
        app = mount / args.app_name
        if not app.is_dir():
            raise FileNotFoundError(f"expected app not found in DMG: {app}")
        smoke_cmd = [
            sys.executable,
            "scripts/smoke_app_runtime.py",
            "--app",
            str(app),
            "--folder",
            args.folder,
            "--timeout",
            str(args.timeout),
        ]
        smoke = subprocess.run(smoke_cmd, cwd=Path(__file__).resolve().parents[1], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        summary = {
            "dmg": str(dmg),
            "device": device,
            "mount_point": mount_point,
            "entries": entries,
            "app": str(app),
            "smoke_returncode": smoke.returncode,
            "smoke_stdout_tail": smoke.stdout.splitlines()[-20:],
            "smoke_stderr_tail": smoke.stderr.splitlines()[-20:],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return smoke.returncode
    finally:
        if device:
            detach(device)


if __name__ == "__main__":
    raise SystemExit(main())
